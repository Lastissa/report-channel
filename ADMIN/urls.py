from django.urls import path

from . import views


app_name = "control"

urlpatterns = [
    path("staff/", views.StaffDirectoryView.as_view(), name="staff_directory"),
    path("staff/<int:staff_id>/", views.StaffDetailView.as_view(), name="staff_detail"),
    path("staff/<int:staff_id>/published/", views.StaffPublishedView.as_view(), name="staff_published"),
    path("staff/<int:staff_id>/tribute/", views.StaffTributeUpdateView.as_view(), name="staff_tribute"),
    path("staff/<int:staff_id>/role/", views.StaffRoleUpdateView.as_view(), name="staff_role"),
    path("staff/<int:staff_id>/status/", views.StaffBanToggleView.as_view(), name="staff_status"),
]
