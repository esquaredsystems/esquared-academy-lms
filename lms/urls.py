"""
URL configuration for the lms project.

    /                  redirects to the admin — the login page when signed out
    /admin/            Django admin
    /admin/home/       a teacher's home: six ways in and nothing else
    /admin/calendar/   their lessons, month by month
    /admin/browse/     class > subject > topic > lectures and assignments
    /admin/my-day/     a teacher's own screen: today's lessons
    /admin/lesson/<id>/materials/   upload lecture material
    /admin/handout/<id>/            print it, hand it out, watch it come back
    /admin/my-subjects/ everything a teacher teaches, and how far ahead
    /admin/checking/   the examiner's queue of work to check
    /admin/my-work/    the student's side: what is open, and handing it in
    /admin/app/        redirects home; the app index duplicated it
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

from app.admin_views import (
    handout_extend_view,
    handout_print_view,
    handout_view,
    lesson_materials_view,
    assignments_view,
    browse_view,
    check_submission_view,
    checking_queue_view,
    checking_browse_view,
    checking_assignment_view,
    approvals_view,
    calendar_view,
    my_day_view,
    new_handout_view,
    my_subjects_view,
    teacher_home_view,
    my_work_view,
    notice_board_view,
    post_notice_view,
)
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
    # Before admin.site.urls so the admin catch-all does not swallow it.
    path(
        # Django's per-application index. It used to list the app's
        # models; now that the dashboard shows the same role panels as the
        # home page it is a second door into the same room, so the "App"
        # breadcrumb goes home instead of rendering a duplicate.
        "admin/app/",
        RedirectView.as_view(pattern_name="admin:index", permanent=False),
    ),
    path(
        "admin/home/",
        admin.site.admin_view(lambda request: teacher_home_view(request, admin.site)),
        name="teacher-home",
    ),
    path(
        "admin/assignments/",
        admin.site.admin_view(lambda request: assignments_view(request, admin.site)),
        name="assignments",
    ),
    path(
        "admin/calendar/",
        admin.site.admin_view(lambda request: calendar_view(request, admin.site)),
        name="calendar",
    ),
    path(
        "admin/browse/",
        admin.site.admin_view(lambda request: browse_view(request, admin.site)),
        name="browse",
    ),
    path(
        "admin/my-day/",
        admin.site.admin_view(lambda request: my_day_view(request, admin.site)),
        name="my-day",
    ),
    path(
        # Upload straight onto a lesson. The admin's own inline only links
        # to a file that already exists.
        "admin/lesson/<int:lesson_id>/materials/",
        admin.site.admin_view(
            lambda request, lesson_id: lesson_materials_view(
                request, lesson_id, admin.site
            )
        ),
        name="lesson-materials",
    ),
    path(
        "admin/lesson/<int:lesson_id>/handout/new/",
        admin.site.admin_view(
            lambda request, lesson_id: new_handout_view(request, lesson_id, admin.site)
        ),
        name="new-handout",
    ),
    path(
        "admin/handout/<int:handout_id>/",
        admin.site.admin_view(
            lambda request, handout_id: handout_view(request, handout_id, admin.site)
        ),
        name="handout",
    ),
    path(
        "admin/handout/<int:handout_id>/extend/",
        admin.site.admin_view(
            lambda request, handout_id: handout_extend_view(
                request, handout_id, admin.site
            )
        ),
        name="handout-extend",
    ),
    path(
        "admin/handout/<int:handout_id>/print/",
        admin.site.admin_view(
            lambda request, handout_id: handout_print_view(
                request, handout_id, admin.site
            )
        ),
        name="handout-print",
    ),
    path(
        "admin/my-subjects/",
        admin.site.admin_view(lambda request: my_subjects_view(request, admin.site)),
        name="my-subjects",
    ),
    path(
        "admin/checking/",
        admin.site.admin_view(lambda request: checking_browse_view(request, admin.site)),
        name="checking-browse",
    ),
    path(
        "admin/checking/waiting/",
        admin.site.admin_view(lambda request: checking_queue_view(request, admin.site)),
        name="checking-queue",
    ),
    path(
        "admin/checking/assignment/<int:handout_id>/",
        admin.site.admin_view(
            lambda request, handout_id: checking_assignment_view(
                request, handout_id, admin.site
            )
        ),
        name="checking-assignment",
    ),
    path(
        "admin/submission/<int:submission_id>/check/",
        admin.site.admin_view(
            lambda request, submission_id: check_submission_view(
                request, submission_id, admin.site
            )
        ),
        name="check-submission",
    ),
    path(
        "admin/my-work/",
        admin.site.admin_view(lambda request: my_work_view(request, admin.site)),
        name="my-work",
    ),
    path(
        "admin/notice-board/",
        admin.site.admin_view(lambda request: notice_board_view(request, admin.site)),
        name="notice-board",
    ),
    path(
        "admin/notice-board/post/",
        admin.site.admin_view(lambda request: post_notice_view(request, admin.site)),
        name="post-notice",
    ),
    path(
        "admin/approvals/",
        admin.site.admin_view(lambda request: approvals_view(request, admin.site)),
        name="approvals",
    ),
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
