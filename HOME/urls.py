from django.urls import path

from . import views


app_name = "home"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/add-news/", views.AddNewsView.as_view(), name="add_news"),
    path("profile/bookmarks/", views.ProfileBookmarksView.as_view(), name="profile_bookmarks"),
    path("profile/history/", views.ProfileHistoryView.as_view(), name="profile_history"),
    path("profile/comments/", views.ProfileCommentsView.as_view(), name="profile_comments"),
    path("profile/stories/", views.ProfilePublishedView.as_view(), name="profile_published"),
    path("profile/settings/newsletter/", views.ProfileNewsletterToggleView.as_view(), name="profile_newsletter_toggle"),
    path("profile/settings/image/", views.ProfileImageUpdateView.as_view(), name="profile_image_update"),
    path("profile/staff/update/", views.ProfileStaffUpdateView.as_view(), name="profile_staff_update"),
    path("load-more/", views.LoadMoreView.as_view(), name="load_more"),
    path("bookmark/<int:blog_id>/", views.BookmarkView.as_view(), name="bookmark"),
    path("newsletter/", views.NewsletterSubscribeView.as_view(), name="newsletter"),
    path("privacy-policy/", views.PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("promote/", views.PromoteView.as_view(), name="promote"),
]

