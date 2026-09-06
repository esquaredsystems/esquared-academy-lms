"""
Send a teacher to their own home rather than to a dashboard.

The dashboard's panels link to database tables. A teacher wants their
day, their subjects, their calendar and their classes — so the admin
home page forwards to /admin/home/ for anyone whose role is teaching
and nothing more.

Anyone who also runs the academy — Admin, Academic Admin, Head of
Department, IT Administrator — keeps the dashboard, because they use it.
And `?home=1` always shows the dashboard, so the redirect is never a
trap.
"""

from django.shortcuts import redirect
from django.urls import reverse

from . import access


class TeacherLandingMiddleware:
    """Forward `/admin/` to `/admin/my-day/` for teaching-only accounts."""

    #: Roles that are given the dashboard instead: they run things, and
    #: the panels are what they came for.
    DASHBOARD_ROLES = {
        access.ADMIN,
        access.ACADEMIC_ADMIN,
        access.IT_ADMIN,
        access.HEAD_OF_DEPARTMENT,
    }

    def __init__(self, get_response):
        self.get_response = get_response
        self.index = reverse("admin:index")
        self.landing = reverse("teacher-home")

    def __call__(self, request):
        if (
            request.method == "GET"
            and request.path == self.index
            and "home" not in request.GET
        ):
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and not user.is_superuser:
                roles = access.role_names(user)
                if access.TEACHING_STAFF in roles and not (roles & self.DASHBOARD_ROLES):
                    return redirect(self.landing)
        return self.get_response(request)
