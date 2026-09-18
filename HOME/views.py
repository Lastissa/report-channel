import logging

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.sessions.models import Session
from django.core.exceptions import BadRequest, ValidationError
from django.core.paginator import Paginator
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import Truncator
from django.views import View

from BLOG.models import Blog, CATEGORY, Comment
from HOME.models import Bookmark
from SERVICE_INTERNAL.abstract import _response, is_rate_limited
from SERVICE_INTERNAL.config import StaffConfig
from SERVICE_INTERNAL.permissions import admin_only, staff_only
from SERVICE_INTERNAL.sessions import drop_sessions_for
from STAFF.models import GENDER_CHOICES, FollowRelationship, StaffProfile

logger = logging.getLogger(__name__)

PAGE_SIZE = 10  #   THE AMOUNT OF NEWs  TO FIRDT LOAD + THE PAGINATION AS WELL
FEATURED_COUNT = 5  #   FEATUREAD


def handler404(request, exception=None):
    """Site wide 404 page. Kept deliberately minimal but still framed by the
    regular header and footer."""
    return render(request, "HOME/404.html", status=404)


def _bookmarked_ids(user):
    if not user.is_authenticated:
        return set()
    return set(Bookmark.objects.filter(user=user).values_list("blog_id", flat=True))


def _page_context(page, user):
    return {
        "page_obj": page,
        "saved_ids": _bookmarked_ids(user),
        "has_more": page.has_next(),
        "next_page": page.next_page_number() if page.has_next() else page.number,
    }


def _resolve_page_number(raw_value, *, default=1):
    if raw_value is None or raw_value == "":
        return default
    try:
        page_number = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise BadRequest("Invalid page number.") from exc
    if page_number < 1:
        raise Http404("Page not found.")
    return page_number


def _user_sessions_for_profile(user, request):
    sessions = []
    for session in Session.objects.filter(session_key__isnull=False).iterator():
        decoded = session.get_decoded() or {}
        if str(decoded.get("_auth_user_id")) != str(user.pk):
            continue

        meta = decoded.get("session_meta") or {}
        login_time = meta.get("logged_in_at")
        if login_time:
            try:
                login_time = timezone.datetime.fromisoformat(login_time)
            except ValueError:
                login_time = None

        expiry = getattr(session, "expire_date", None)
        if expiry is None and hasattr(session, "get_expiry_date"):
            try:
                expiry = session.get_expiry_date()
            except (AttributeError, TypeError, ValueError):
                expiry = None

        sessions.append(
            {
                "session_key": session.session_key,
                "ip": meta.get("ip") or "Unknown IP",
                "device": meta.get("user_agent") or "Unknown device",
                "logged_in_at": login_time,
                "expires_at": expiry,
                "is_current": session.session_key == request.session.session_key,
            }
        )

    sessions.sort(key=lambda item: (item["is_current"], item["logged_in_at"] or timezone.now()), reverse=True)
    return sessions


class HomeView(View):
    """Landing page: hero carousel of featured stories and paginated story grid."""

    def get(self, request):
        #q = the actual heading to filter
        #category = self explatory
        query = request.GET.get("q", "").strip()
        category = request.GET.get("category", "").strip().upper()
        page_number = _resolve_page_number(request.GET.get("page"), default=1)

        base_qs = Blog.objects.select_related("author").order_by("-date_created")

        if query:
            base_qs = base_qs.filter(heading__icontains=query)
        if category:
            base_qs = base_qs.filter(category=category)

        is_filtered = bool(query or category)

        featured = [] if is_filtered else list(base_qs[:FEATURED_COUNT])
        featured_ids = [post.id for post in featured]

        grid_qs = base_qs.exclude(id__in=featured_ids)
        paginator = Paginator(grid_qs, PAGE_SIZE)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")
        page = paginator.get_page(page_number)

        context = {
            "featured_posts": featured,
            "categories": CATEGORY,
            "query": query,
            "active_category": category,
            "is_filtered": is_filtered,
            "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
            **_page_context(page, request.user),
        }
        from SERVICE_INTERNAL.abstract import _optimization
        _optimization()
        return render(request, "HOME/home.html", context)


class LoadMoreView(View):
    """Returns the next page of story cards for the "Load more" button."""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        category = request.GET.get("category", "").strip().upper()
        page_number = _resolve_page_number(request.GET.get("page"), default=2)

        base_qs = Blog.objects.select_related("author").order_by("-date_created")
        if query:
            base_qs = base_qs.filter(heading__icontains=query)
        if category:
            base_qs = base_qs.filter(category=category)

        is_filtered = bool(query or category)
        featured_ids = [] if is_filtered else list(base_qs[:FEATURED_COUNT].values_list("id", flat=True))
        grid_qs = base_qs.exclude(id__in=featured_ids)

        paginator = Paginator(grid_qs, PAGE_SIZE)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")
        page = paginator.get_page(page_number)
        return render(
            request,
            "HOME/partials/story_cards.html",
            {**_page_context(page, request.user), "next_page": page.next_page_number() if page.has_next() else None},
        )


class BookmarkView(View):
    """Demo endpoint: toggles a bookmark for the logged in user. Always
    returns a JSON body with a `detail` key, status code carries the meaning."""

    def post(self, request, blog_id):
        print(request.user or "Anony")
        if not request.user.is_authenticated:
            return _response({"detail": "Sign in to save stories."}, status=401)

        try:
            blog = Blog.objects.get(pk=blog_id)
        except Blog.DoesNotExist:
            return _response({"detail": "Story not found."}, status=404)

        existing = Bookmark.objects.filter(user=request.user, blog=blog).first()
        if existing:
            remaining_time, is_limited = is_rate_limited(request, 10, 2, False)
            if is_limited:
                unit = "second" if remaining_time == 1 else "seconds"
                return _response(
                    {"detail": f"Too many bookmark removals. Try again in {remaining_time} {unit}."},
                    status=429,
                )
            existing.delete()
            return _response({"detail": "Removed from bookmarks.", "bookmarked": False, "bookmark_count": blog.bookmarked_by.count()}, status=200)

        Bookmark.objects.create(user=request.user, blog=blog)
        return _response({"detail": "Saved to bookmarks.", "bookmarked": True, "bookmark_count": blog.bookmarked_by.count()}, status=201)


class AddNewsView(View):
    """Staff only two pane story editor. GET serves the split loading page,
    POST validates and publishes the story."""

    def dispatch(self, request, *args, **kwargs):
        if not staff_only(request.user):
            return redirect("home:profile")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, "HOME/add_news.html")

    def post(self, request):
        heading = (request.POST.get("heading") or "").strip()
        image_url = (request.POST.get("image_1") or "").strip()
        image_info = (request.POST.get("image_info") or "").strip()
        category = (request.POST.get("category") or "").strip().upper()
        content = (request.POST.get("content") or "").strip()

        if not heading:
            return _response({"detail": "The heading cannot be empty."}, status=400)
        if len(heading) > 100:
            return _response({"detail": "The heading is limited to 100 characters."}, status=400)
        if category not in {value for value, _ in CATEGORY}:
            return _response({"detail": "Select a valid category."}, status=400)
        if not content:
            return _response({"detail": "The story content cannot be empty."}, status=400)

        if image_url:
            validator = URLValidator(schemes=["http", "https"])
            try:
                validator(image_url)
            except ValidationError:
                return _response({"detail": "The image link must be a valid http or https URL."}, status=400)

        #   THE SAME AUTHOR CANNOT PUBLISH THE SAME HEADING INTO THE SAME
        #   CATEGORY TWICE (mirrors the database constraint on Blog)
        if Blog.objects.filter(author=request.user, category=category, heading__iexact=heading).exists():
            return _response(
                {"detail": "You already have a story with this exact heading in this category. Edit the heading or choose a different category."},
                status=400,
            )

        try:
            blog_data = dict(
                author=request.user,
                heading=heading,
                image_1=image_url or None,
                category=category,
                content=content,
            )
            if image_info:
                blog_data["image_info"] = image_info
            blog = Blog.objects.create(**blog_data)
        except IntegrityError:
            return _response(
                {"detail": "You already have a story with this exact heading in this category. Edit the heading or choose a different category."},
                status=400,
            )
        return _response(
            {"detail": "Story published.", "story_url": f"/story/{blog.pk}/", "id": blog.pk},
            status=201,
        )


class NewsletterSubscribeView(View):
    """Collects an email for the newsletter. No dedicated table yet -- logged
    server side only, per project decision."""

    def post(self, request):
        email = request.POST.get("email", "").strip()
        if not email or "@" not in email:
            return _response({"detail": "Enter a valid email address."}, status=400)

        logger.info("NEWSLETTER SIGNUP: %s", email)
        return _response({"detail": "You're on the list."}, status=201)


class PrivacyPolicyView(View):
    def get(self, request):
        return render(request, "HOME/privacy_policy.html")


class PromoteView(View):
    """Dummy placeholder for the footer's 'promote your business' banner.
    No form/backend logic yet -- just a page to land on until that flow
    is designed."""

    def get(self, request):
        return render(request, "HOME/promote.html")


class ProfileNewsletterToggleView(View):
    """Toggle newsletter delivery without a full page refresh."""

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in to update settings.", "enabled": False}, status=401)

        current_state = bool(getattr(request.user, "receive_email_login_alert", True))
        new_state = not current_state
        request.user.receive_email_login_alert = new_state
        request.user.save(update_fields=["receive_email_login_alert"])

        return JsonResponse(
            {
                "detail": "Newsletter updates enabled." if new_state else "Newsletter updates disabled.",
                "enabled": new_state,
                "status": "on" if new_state else "off",
            },
            status=200,
        )


class ProfileBlogNotificationToggleView(View):
    """Toggle post-view reminders for staff. This is a staff level setting,
    not an admin power, so it lives with the other profile toggles rather
    than in the ADMIN app."""

    def post(self, request):
        if not staff_only(request.user):
            return JsonResponse({"detail": "Staff access is required.", "enabled": False}, status=403)

        profile = StaffProfile.objects.filter(auth=request.user).first()
        if profile is None:
            return JsonResponse(
                {"detail": "No staff profile on this account yet. Save your staff profile first.", "enabled": False},
                status=409,
            )

        new_state = not profile.get_blog_notification
        profile.get_blog_notification = new_state
        profile.save(update_fields=["get_blog_notification"])

        return JsonResponse(
            {
                "detail": "Story view reminders enabled." if new_state else "Story view reminders disabled.",
                "enabled": new_state,
                "status": "on" if new_state else "off",
            },
            status=200,
        )


class ProfileLogoutAllSessionsView(View):
    """End every session the signed in user holds, the current one included.

    The response is JSON because the fetch caller redirects to the login
    page itself: the session that made this request is gone by the time the
    response arrives.
    """

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in first."}, status=401)

        remaining_time, is_limited = is_rate_limited(request, 30, 2)
        if is_limited:
            return JsonResponse({"detail": f"Too many attempts. Wait {remaining_time} seconds."}, status=429)

        email = request.user.email
        dropped = drop_sessions_for(request.user)
        #   flush() clears whatever the session middleware would otherwise
        #   re-save for this request, so this browser is signed out too.
        auth_logout(request)
        logger.info("ACCOUNT LOGOUT ALL: %s ended %d session(s)", email, dropped)

        return JsonResponse(
            {
                "detail": f"Signed out of {dropped} session(s).",
                "sessions_ended": dropped,
                "redirect_to": reverse("auth:login"),
            },
            status=200,
        )


class ProfileImageUpdateView(View):
    """Validate and save a new profile image URL."""

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in to update your profile image.", "valid": False}, status=401)

        image_url = (request.POST.get("image_url") or "").strip()
        if not image_url:
            return JsonResponse({"detail": "Please add a valid image URL.", "valid": False}, status=400)

        validator = URLValidator(schemes=["http", "https"])
        try:
            validator(image_url)
        except ValidationError:
            return JsonResponse({"detail": "The URL must be a valid http or https link.", "valid": False}, status=400)

        #   RATE LIMIT THE ENDPOINT JUST BEFORE DATABASE UPLOAD
        remaining_time, is_limited = is_rate_limited(request, 30, 2,False)
        if is_limited: return JsonResponse({'detail': f'too frequent update. Retry in {str(remaining_time) + "seconds" if remaining_time>1 else str(remaining_time)+" second"}'}, status = 429)
        request.user.profile_img = image_url
        request.user.save(update_fields=["profile_img"])
        return JsonResponse({"detail": "Profile image updated.", "valid": True, "image_url": image_url}, status=200)


class ProfileBookmarksView(View):
    """Return a paginated bookmark payload for the profile page."""

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in to view bookmarks."}, status=401)

        page_number = _resolve_page_number(request.GET.get("page"), default=1)
        bookmarks_qs = Bookmark.objects.filter(user=request.user).select_related("blog").order_by("-created_at")
        paginator = Paginator(bookmarks_qs, 5)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")

        page = paginator.get_page(page_number)
        items = [
            {
                "id": bookmark.id,
                "blog_id": bookmark.blog_id,
                "heading": bookmark.blog.heading,
                "created_at": bookmark.created_at.isoformat(),
                "url": f"/blog/{bookmark.blog_id}/",
            }
            for bookmark in page.object_list
        ]

        return JsonResponse(
            {
                "items": items,
                "page": page.number,
                "num_pages": paginator.num_pages,
                "has_previous": page.has_previous(),
                "has_next": page.has_next(),
                "next_page": page.next_page_number() if page.has_next() else None,
                "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
                "count": paginator.count,
            },
            status=200,
        )


class ProfileHistoryView(View):
    """Return a paginated reading-history payload for the profile page."""

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in to view history."}, status=401)

        page_number = _resolve_page_number(request.GET.get("page"), default=1)
        history_qs = Blog.objects.filter(non_anonymous_viewer=request.user).order_by("-date_created")
        paginator = Paginator(history_qs, 5)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")

        page = paginator.get_page(page_number)
        items = [
            {
                "id": blog.id,
                "blog_id": blog.id,
                "heading": blog.heading,
                "date_created": blog.date_created.isoformat(),
                "url": f"/blog/{blog.id}/",
            }
            for blog in page.object_list
        ]

        return JsonResponse(
            {
                "items": items,
                "page": page.number,
                "num_pages": paginator.num_pages,
                "has_previous": page.has_previous(),
                "has_next": page.has_next(),
                "next_page": page.next_page_number() if page.has_next() else None,
                "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
                "count": paginator.count,
            },
            status=200,
        )


class ProfileCommentsView(View):
    """Return a paginated comment-history payload for the profile page."""

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Please sign in to view comments."}, status=401)

        page_number = _resolve_page_number(request.GET.get("page"), default=1)
        comments_qs = Comment.objects.filter(author=request.user).select_related("blog").order_by("-id")
        paginator = Paginator(comments_qs, 5)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")

        page = paginator.get_page(page_number)
        items = [
            {
                "id": comment.id,
                "blog_id": comment.blog_id,
                "heading": comment.blog.heading,
                "excerpt": Truncator(comment.content).chars(85),
                "url": f"/blog/{comment.blog_id}/",
            }
            for comment in page.object_list
        ]

        return JsonResponse(
            {
                "items": items,
                "page": page.number,
                "num_pages": paginator.num_pages,
                "has_previous": page.has_previous(),
                "has_next": page.has_next(),
                "next_page": page.next_page_number() if page.has_next() else None,
                "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
                "count": paginator.count,
            },
            status=200,
        )


class ProfileStaffUpdateView(View):
    """Staff self-service profile updates with per-field permissions.

    full_name, socials and bio are editable by any staff account. gender and
    speciality are admin/superuser only (their inputs are disabled for plain
    staff so those keys never reach the POST). role is assigned at
    registration and is never accepted from this endpoint.
    """

    def post(self, request):
        remaining_time, is_limited = is_rate_limited(request, 10, 3)
        if is_limited:
            return _response({'detail': f'please, wait {remaining_time} seconds before trying again'}, status=429)
        if not staff_only(request.user):
            return JsonResponse({"detail": "Staff access is required!. Refresh Page"}, status=403)

        profile, _ = StaffProfile.objects.get_or_create(auth=request.user)

        full_name = (request.POST.get("full_name") or "").strip()
        if not full_name:
            return JsonResponse({"detail": "Full name cannot be empty."}, status=400)
        if len(full_name) > 100:
            return JsonResponse({"detail": "Full name is limited to 100 characters."}, status=400)
        profile.full_name = full_name

        profile.bio = (request.POST.get("bio") or "").strip()

        validator = URLValidator(schemes=["http", "https"])
        for field in ("twitter_handle", "facebook_handle", "whatsapp_handle"):
            value = (request.POST.get(field) or "").strip()
            if value:
                try:
                    validator(value)
                except ValidationError:
                    return JsonResponse({"detail": f"The {field.replace('_handle', '')} link must be a valid http or https URL."}, status=400)
            setattr(profile, field, value or None)

        editable_fields = ["full_name", "bio", "twitter_handle", "facebook_handle", "whatsapp_handle"]

        is_admin = admin_only(request.user)
        if "gender" in request.POST:
            if not is_admin:
                return JsonResponse({"detail": "Only admins can change gender."}, status=403)
            gender = request.POST.get("gender", "")
            if gender not in {value for value, _ in GENDER_CHOICES}:
                return JsonResponse({"detail": "Select a valid gender option."}, status=400)
            profile.gender = gender
            editable_fields.append("gender")

        if "speciality" in request.POST:
            if not is_admin:
                return JsonResponse({"detail": "Only admins can change speciality."}, status=403)
            raw = request.POST.get("speciality", "")
            profile.speciality = [part.strip() for part in raw.split(",") if part.strip()]
            editable_fields.append("speciality")

        profile.save(update_fields=editable_fields)

        return JsonResponse(
            {
                "detail": "Staff profile updated.",
                "full_name": profile.full_name,
                "gender": profile.gender,
                "speciality_csv": ", ".join(profile.speciality) if isinstance(profile.speciality, list) else "",
                "bio": profile.bio,
                "twitter_handle": profile.twitter_handle or "",
                "facebook_handle": profile.facebook_handle or "",
                "whatsapp_handle": profile.whatsapp_handle or "",
                "role_display": profile.get_role_display(),
            },
            status=200,
        )


class ProfilePublishedView(View):
    """Return a paginated published-stories payload for the staff profile."""

    def get(self, request):
        if not staff_only(request.user):
            return JsonResponse({"detail": "Staff access is required to view published stories!. Refresh Page"}, status=401)

        page_number = _resolve_page_number(request.GET.get("page"), default=1)
        published_qs = Blog.objects.filter(author=request.user).order_by("-date_created")
        paginator = Paginator(published_qs, 5)
        if page_number > paginator.num_pages and paginator.num_pages:
            raise Http404("Page not found.")

        page = paginator.get_page(page_number)
        items = [
            {
                "id": blog.id,
                "blog_id": blog.id,
                "heading": blog.heading,
                "views": blog.views,
                "date_created": blog.date_created.isoformat(),
                "url": f"/story/{blog.id}/",
            }
            for blog in page.object_list
        ]

        return JsonResponse(
            {
                "items": items,
                "page": page.number,
                "num_pages": paginator.num_pages,
                "has_previous": page.has_previous(),
                "has_next": page.has_next(),
                "next_page": page.next_page_number() if page.has_next() else None,
                "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
                "count": paginator.count,
            },
            status=200,
        )


class ProfilePublishedDeleteView(View):
    """Delete a story from its author's profile dashboard."""

    def post(self, request, blog_id):
        if not staff_only(request.user):
            return JsonResponse({"detail": "Staff access is required to delete a story!. Refresh Page"}, status=403)

        blog = Blog.objects.filter(pk=blog_id, author=request.user).first()
        if blog is None:
            return JsonResponse({"detail": "Story not found."}, status=404)

        blog.delete()
        return JsonResponse({"detail": "Story deleted.", "id": blog_id}, status=200)


class ProfileView(View):
    """Shared profile dashboard for any authenticated user."""

    def get(self, request):
        if not request.user.is_authenticated:
            messages.info(request, "Please sign in to open your profile.")
            return redirect("auth:login")

        profile = StaffProfile.objects.filter(auth=request.user).first()
        bookmark_qs = Bookmark.objects.filter(user=request.user).select_related("blog").order_by("-created_at")
        bookmark_page_number = _resolve_page_number(request.GET.get("page"), default=1)
        bookmark_paginator = Paginator(bookmark_qs, 5)
        if bookmark_page_number > bookmark_paginator.num_pages and bookmark_paginator.num_pages:
            raise Http404("Page not found.")
        bookmark_page = bookmark_paginator.get_page(bookmark_page_number)

        recent_bookmarks = bookmark_page.object_list
        reading_history_qs = Blog.objects.filter(non_anonymous_viewer=request.user).order_by("-date_created")
        history_page_number = _resolve_page_number(request.GET.get("history_page"), default=1)
        history_paginator = Paginator(reading_history_qs, 5)
        if history_page_number > history_paginator.num_pages and history_paginator.num_pages:
            raise Http404("Page not found.")
        history_page = history_paginator.get_page(history_page_number)

        comments_qs = Comment.objects.filter(author=request.user).select_related("blog").order_by("-id")
        comments_page_number = _resolve_page_number(request.GET.get("comments_page"), default=1)
        comments_paginator = Paginator(comments_qs, 5)
        if comments_page_number > comments_paginator.num_pages and comments_paginator.num_pages:
            raise Http404("Page not found.")
        comments_page = comments_paginator.get_page(comments_page_number)

        published_qs = Blog.objects.filter(author=request.user).order_by("-date_created")
        stories_page_number = _resolve_page_number(request.GET.get("stories_page"), default=1)
        stories_paginator = Paginator(published_qs, 5)
        if stories_page_number > stories_paginator.num_pages and stories_paginator.num_pages:
            raise Http404("Page not found.")
        stories_page = stories_paginator.get_page(stories_page_number)

        #   ADMIN AUTHORITY PANEL: the staff directory only loads for admins
        #   and superusers, deferred import keeps ADMIN.views free to import
        #   from HOME.views without a circular reference.
        staff_directory = []
        staff_directory_page_obj = None
        staff_directory_page_range = []
        if admin_only(request.user):
            from ADMIN.views import staff_directory_page, staff_directory_rows

            staff_page_number = _resolve_page_number(request.GET.get("staff_page"), default=1)
            staff_paginator, staff_page = staff_directory_page(staff_page_number)
            staff_directory = staff_directory_rows(list(staff_page.object_list))
            staff_directory_page_obj = staff_page
            staff_directory_page_range = list(
                staff_paginator.get_elided_page_range(staff_page.number, on_each_side=1, on_ends=1)
            )

        follower_count = FollowRelationship.objects.filter(followee_id=profile.id).count() if profile else 0
        following_count = FollowRelationship.objects.filter(follower_id=profile.id).count() if profile else 0

        #   Own-role select: only admins and superusers get the choices in
        #   context, so non-admin pages pay nothing for it.
        is_admin = admin_only(request.user)

        context = {
            "profile": profile,
            "user": request.user,
            "recent_bookmarks": recent_bookmarks,
            "bookmark_page_obj": bookmark_page,
            "bookmark_page_range": list(bookmark_paginator.get_elided_page_range(bookmark_page.number, on_each_side=1, on_ends=1)),
            "reading_history": history_page.object_list,
            "history_page_obj": history_page,
            "history_page_range": list(history_paginator.get_elided_page_range(history_page.number, on_each_side=1, on_ends=1)),
            "recent_comments": comments_page.object_list,
            "comments_page_obj": comments_page,
            "comments_page_range": list(comments_paginator.get_elided_page_range(comments_page.number, on_each_side=1, on_ends=1)),
            "published_stories": stories_page.object_list,
            "stories_page_obj": stories_page,
            "stories_page_range": list(stories_paginator.get_elided_page_range(stories_page.number, on_each_side=1, on_ends=1)),
            "follower_count": follower_count,
            "following_count": following_count,
            "is_staff_user": staff_only(request.user),
            "is_admin_user": is_admin,
            "show_staff_dashboard": staff_only(request.user),
            "user_sessions": _user_sessions_for_profile(request.user, request),
            "gender_choices": GENDER_CHOICES,
            "role_choices": StaffConfig.role_choices() if is_admin else [],
            "protected_roles": sorted(StaffConfig.PROTECTED_ROLES) if is_admin else [],
            "staff_directory": staff_directory,
            "staff_directory_page_obj": staff_directory_page_obj,
            "staff_directory_page_range": staff_directory_page_range,
            "speciality_csv": ", ".join(profile.speciality) if profile and isinstance(profile.speciality, list) else "",
        }
        return render(request, "HOME/profile.html", context)
