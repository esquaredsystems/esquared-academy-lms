"""
URL configuration for the lms project.

    /                  redirects to the admin — the login page when signed out
    /admin/            Django admin
    /admin/app/attachment/upload/   drag-and-drop uploader
    /media/            uploaded files (development only — see README)
    /api/              REST API (see app/urls.py for the resource list)
    /api/schema/       OpenAPI 3 schema (YAML)
    /api/docs/         Swagger UI
    /api/redoc/        ReDoc
    /api-auth/         DRF session login, for the browsable API
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # There is no public site yet, so the root is the admin. Anonymous
    # visitors land on the admin login page; signed-in staff go straight
    # to the dashboard.
    path("", RedirectView.as_view(pattern_name="admin:index", permanent=False), name="home"),
    path("jet/", include("jet.urls", "jet")),
    path("jet/dashboard/", include("jet.dashboard.urls", "jet-dashboard")),
    path("admin/", admin.site.urls),
    path("api/", include("app.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    # runserver only. In production the web server serves MEDIA_ROOT, or
    # the files move to object storage — see the README.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
