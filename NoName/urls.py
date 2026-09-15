
from django.contrib import admin
from django.urls import include, path

handler404 = "HOME.views.handler404"

urlpatterns = [
    path('sy/', include("_.urls")),
    path('_admin/', admin.site.urls),
    path('auth/', include("AUTHENTICATION.urls")),
    path('story/', include("BLOG.urls")),
    path('', include("HOME.urls")),
]


