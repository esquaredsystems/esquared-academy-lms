"""
URL configuration for the lms project.

    /admin/            Django admin
    /api/              REST API (see app/urls.py for the resource list)
    /api/schema/       OpenAPI 3 schema (YAML)
    /api/docs/         Swagger UI
    /api/redoc/        ReDoc
    /api-auth/         DRF session login, for the browsable API
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
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
