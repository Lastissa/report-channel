import html
import re

from django.db.models import F, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from AUTHENTICATION.models import Auth
from SERVICE_INTERNAL.abstract import _optimization
from STAFF.models import StaffProfile
from .models import Blog, Comment

URL_RE = re.compile(r"https?://[^\s<>'\"]+")

STORY_404_CONTENT = (
    "This page does not exist. We may not have enough stories published yet, "
    "or the story you are looking for was deleted by the publisher and is no "
    "longer in existence.".upper()
)


def _linkify_text(value):
    """Turn URL-like tokens into anchor tags while preserving normal text."""
    safe_text = html.escape(value, quote=False)
    safe_text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe_text)
    safe_text = re.sub(r"__(.+?)__", r"<em>\1</em>", safe_text)
    safe_text = URL_RE.sub(lambda match: f'<a href="{match.group(0)}" rel="noopener noreferrer" target="_blank">{match.group(0)}</a>', safe_text)
    return safe_text


def parse_story_content(content):
    """Render story text into a readable article structure with SEO-friendly blocks."""
    if not content:
        return ""

    lines = [line.rstrip() for line in content.strip().splitlines()]
    blocks = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        heading_match = re.match(r"^(#+)\s*(.*)$", line)
        if heading_match:
            heading_level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            if heading_text:
                tag_level = min(heading_level + 1, 4)
                blocks.append(f'<h{tag_level}>{_linkify_text(heading_text)}</h{tag_level}>')
            i += 1
            continue

        if re.match(r"^\*\s+", line):
            items = []
            while i < len(lines):
                current = lines[i].strip()
                if not current or not re.match(r"^\*\s+", current):
                    break
                items.append(current[2:].strip())
                i += 1
            blocks.append('<ul>' + ''.join(f'<li>{_linkify_text(item)}</li>' for item in items if item) + '</ul>')
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines):
                current = lines[i].strip()
                if not current or not re.match(r"^\d+\.\s+", current):
                    break
                match = re.match(r"^\d+\.\s+(.*)$", current)
                if match:
                    items.append(match.group(1).strip())
                i += 1
            blocks.append('<ol>' + ''.join(f'<li>{_linkify_text(item)}</li>' for item in items if item) + '</ol>')
            continue

        paragraph_lines = []
        while i < len(lines):
            current = lines[i].strip()
            if not current:
                break
            if re.match(r"^(#+\s+|\*\s+|\d+\.\s+)", current):
                break
            paragraph_lines.append(current)
            i += 1
            if i < len(lines) and not lines[i].strip():
                break

        paragraph = ' '.join(paragraph_lines).strip()
        if paragraph:
            blocks.append(f'<p>{_linkify_text(paragraph)}</p>')

    return '\n'.join(blocks)


class StoryDetailView(View):
    def get(self, request, blog_id):
        blog = Blog.objects.filter(pk=blog_id).select_related("author").first()
        if blog is None:
            #   DECOY PAGE: missing stories still render as a normal looking
            #   article but nothing on it is real, so no views, history or
            #   comments are tracked for it.
            return render(
                request,
                "blog/story_404.html",
                {"blog_id": blog_id, "decoy_content": STORY_404_CONTENT},
                status=404,
            )
        blog_content = parse_story_content(blog.content)
        comments = (
            blog.comments.select_related("author")
            .prefetch_related(
                Prefetch(
                    "author__staffprofile_set",
                    queryset=StaffProfile.objects.only("auth_id", "full_name"),
                    to_attr="author_profiles",
                )
            )
            .order_by("id")
        )
        author_profile = StaffProfile.objects.filter(auth=blog.author).first()

        author_tags = []
        if author_profile and isinstance(author_profile.speciality, list):
            author_tags = [str(tag).strip() for tag in author_profile.speciality if str(tag).strip()]

        author_recent_stories = (
            Blog.objects.filter(author=blog.author)
            .exclude(pk=blog.pk)
            .order_by("-date_created")[:3]
        )

        Blog.objects.filter(pk=blog.pk).update(views=F("views") + 1)
        blog.refresh_from_db(fields=["views"])

        if request.user.is_authenticated:
            blog.non_anonymous_viewer.add(request.user)

        is_bookmarked = request.user.is_authenticated and blog.bookmarked_by.filter(user=request.user).exists()

        context = {
            "blog": blog,
            "blog_content_html": blog_content,
            "comments": comments,
            "author_profile": author_profile,
            "author_tags": author_tags,
            "author_recent_stories": author_recent_stories,
            "is_bookmarked": is_bookmarked,
            "bookmark_count": blog.bookmarked_by.count(),
            "social_links": [
                ("Twitter", author_profile.twitter_handle if author_profile else "#"),
                ("Facebook", author_profile.facebook_handle if author_profile else "#"),
                ("WhatsApp", author_profile.whatsapp_handle if author_profile else "#"),
            ],
        }
        return render(request, "blog/story_detail.html", context)


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _authenticated_user(request):
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user

    user_id = request.session.get("_auth_user_id")
    if user_id:
        session_user = Auth.objects.filter(pk=user_id, is_active=True).first()
        if session_user:
            request.user = session_user
            return session_user
    return None


class BookmarkNotFoundView(View):
    """Bookmark endpoint for the decoy 404 story page. It must never succeed:
    there is no story to attach a Bookmark row to, so every attempt gets the
    same error and the page's optimistic UI reverts itself."""

    def post(self, request):
        return JsonResponse({"detail": "Cannot bookmark, report to developer."}, status=400)


class BlogLikeView(View):
    def post(self, request, blog_id):
        blog = get_object_or_404(Blog, pk=blog_id)
        user = _authenticated_user(request)
        if not user:
            if _is_ajax(request):
                return JsonResponse({"detail": "Please sign in to like this story."}, status=401)
            return redirect("auth:login")

        liked_blogs = request.session.get("liked_blogs", [])
        if blog.id in liked_blogs:
            return JsonResponse({"detail": "You already liked this story.", "likes": blog.likes or 0}, status=200)

        blog.likes = (blog.likes or 0) + 1
        blog.save(update_fields=["likes"])
        liked_blogs = list(dict.fromkeys([*liked_blogs, blog.id]))
        request.session["liked_blogs"] = liked_blogs
        request.session.modified = True

        return JsonResponse({"detail": "Story liked.", "likes": blog.likes}, status=200)

class CommentCreateView(View):
    def post(self, request, blog_id):
        blog = get_object_or_404(Blog, pk=blog_id)
        user = _authenticated_user(request)
        if not user:
            if _is_ajax(request):
                return JsonResponse({"detail": "Please sign in to comment."}, status=401)
            return redirect("auth:login")

        content = (request.POST.get("comment", "") or "").strip()
        if not content or len(content) < 2:
            return JsonResponse({"detail": "Comment cannot be empty."}, status=400)

        if Comment.objects.filter(blog=blog, author=user).exists():
            return JsonResponse({"detail": "You can only post one comment per story."}, status=400)

        comment = Comment.objects.create(blog=blog, author=user, content=content)
        if _is_ajax(request):
            return JsonResponse({"detail": "Comment posted.", "comment_id": comment.id, "comment_count": blog.comments.count(), "content": comment.content}, status=201)
        return redirect("blog:story_detail", blog_id=blog.pk)


class CommentDeleteView(View):
    def post(self, request, comment_id):
        comment = get_object_or_404(Comment, pk=comment_id)
        user = _authenticated_user(request)
        if not user:
            if _is_ajax(request):
                return JsonResponse({"detail": "Please sign in."}, status=401)
            return redirect("auth:login")

        if comment.author_id != user.id and not user.is_staff:
            return JsonResponse({"detail": "You can only delete your own comment."}, status=403)

        blog_id = comment.blog_id
        comment.delete()
        if _is_ajax(request):
            return JsonResponse({"detail": "Comment deleted.", "comment_count": Comment.objects.filter(blog_id=blog_id).count()}, status=200)
        return redirect("blog:story_detail", blog_id=blog_id)


class CommentLikeView(View):
    def post(self, request, comment_id):
        comment = get_object_or_404(Comment, pk=comment_id)
        user = _authenticated_user(request)
        if not user:
            if _is_ajax(request):
                return JsonResponse({"detail": "Please sign in to like this comment."}, status=401)
            return redirect("auth:login")

        liked_comments = request.session.get("liked_comments", [])
        if comment.id in liked_comments:
            return JsonResponse({"detail": "You already liked this comment.", "likes": comment.likes or 0}, status=200)

        comment.likes = (comment.likes or 0) + 1
        comment.save(update_fields=["likes"])
        liked_comments = list(dict.fromkeys([*liked_comments, comment.id]))
        request.session["liked_comments"] = liked_comments
        request.session.modified = True

        return JsonResponse({"detail": "Comment liked.", "likes": comment.likes}, status=200)
