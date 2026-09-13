"""
The admin home page, built for whoever is looking at it.

Jet's default dashboard lists every table the signed-in user has any
permission on, alphabetically, beside links to Django's documentation and
IRC channel. That is a developer's index. A teacher opening it at 7am
needs their lessons, not `Cohort memberships` and a mailing list.

So each role gets its own set of panels, holding the handful of things
that role actually works with. Everything else stays reachable through
the left menu and by URL — this decides what is *offered*, not what is
allowed. Permissions do that, in `app/access.py`.

Wired up by JET_INDEX_DASHBOARD in lms/settings.py.
"""

from django.utils.translation import gettext_lazy as _
from jet.dashboard import modules
from jet.dashboard.dashboard import AppIndexDashboard, Dashboard

from . import access


def _roles(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return set(), None
    return access.role_names(user), user


class _RolePanelsMixin:
    """
    The panels themselves, shared by both dashboards.

    Jet has two: one for the admin home page, and a separate one for the
    per-application page reached from the "App" breadcrumb. Left alone,
    the second falls back to Jet's default, which lists every model again
    — so both are built from the same method here.
    """

    columns = 2

    def init_with_context(self, context):
        roles, user = _roles(context)
        if user is None:
            return

        superuser = bool(getattr(user, "is_superuser", False))

        def has(*names):
            return superuser or bool(roles & set(names))

        column = 0

        # -- Teaching --------------------------------------------------
        if has(access.TEACHER):
            # The first thing on the page, and the one a teacher actually
            # opens each morning. The model lists below are the filing
            # cabinet behind it.
            self.children.append(modules.LinkList(
                _("Start here"),
                children=[
                    {"title": _("My day"), "url": "/admin/my-day/"},
                    {"title": _("My subjects"), "url": "/admin/my-subjects/"},
                ],
                column=column, order=0,
            ))
            self.children.append(modules.ModelList(
                _("Handouts and work"),
                models=("app.Handout", "app.Submission"),
                column=column, order=2,
            ))
            self.children.append(modules.ModelList(
                _("My teaching"),
                models=("app.Lesson", "app.LessonTopic", "app.TimetableSlot"),
                column=column, order=1,
            ))
            self.children.append(modules.ModelList(
                _("My students"),
                models=("app.Student", "app.Enrolment", "app.StudentSubject",
                        "app.TopicResult", "app.StudentCohort"),
                column=column, order=3,
            ))
            column = 1

        # -- Academic authority ----------------------------------------
        if has(access.ADMINISTRATOR):
            self.children.append(modules.LinkList(
                _("To review"),
                children=[
                    {"title": _("Lessons awaiting review"),
                     "url": "/admin/app/lesson/?status__exact=submitted"},
                    {"title": _("Lessons returned for changes"),
                     "url": "/admin/app/lesson/?status__exact=returned"},
                    {"title": _("Draft papers"),
                     "url": "/admin/app/paperversion/?status__exact=draft"},
                ],
                column=0, order=0,
            ))
            self.children.append(modules.ModelList(
                _("Curriculum"),
                models=("app.Subject", "app.Syllabus", "app.AcademyClass"),
                column=1, order=0,
            ))
            column = 1

        # -- Paper setting ---------------------------------------------
        if has(access.TEACHER):
            self.children.append(modules.ModelList(
                _("Question bank"),
                models=("app.Question", "app.QuestionAttributeType", "app.QuestionAttribute",
                        "app.EvaluationPrompt", "app.PromptVersion"),
                column=0, order=1,
            ))
            self.children.append(modules.ModelList(
                _("Papers"),
                models=("app.QuestionPaper", "app.PaperVersion", "app.PaperItem"),
                column=1, order=1,
            ))

        # -- Marking ---------------------------------------------------
        if has(access.EXAMINER):
            self.children.append(modules.LinkList(
                _("Start here"),
                children=[
                    {"title": _("Checking — work waiting"), "url": "/admin/checking/"},
                ],
                column=0, order=0,
            ))
            self.children.append(modules.ModelList(
                _("Marking"),
                models=("app.Attempt", "app.Answer", "app.Evaluation",
                        "app.TopicResult"),
                column=0, order=2,
            ))

        # -- Exam operations -------------------------------------------
        if has(access.EXAMINER):
            self.children.append(modules.ModelList(
                _("Scripts and uploads"),
                models=("app.Attachment", "app.AttachmentLink",
                        "app.UploadSession", "app.Attempt"),
                column=0, order=3,
            ))

        # -- Office ----------------------------------------------------
        if has(access.ADMINISTRATOR):
            self.children.append(modules.ModelList(
                _("Attendance"),
                models=("app.AttendanceSession", "app.AttendanceRecord"),
                column=0, order=4,
            ))
            self.children.append(modules.ModelList(
                _("Students"),
                models=("app.Student", "app.Enrolment", "app.AcademyClass"),
                column=1, order=4,
            ))

        # -- Running the academy ---------------------------------------
        if has(access.ADMINISTRATOR):
            self.children.append(modules.ModelList(
                _("People"),
                models=("app.Student", "app.Teacher", "app.Enrolment"),
                column=1, order=2,
            ))

        # -- Keeping the system running --------------------------------
        if has(access.ADMINISTRATOR):
            self.children.append(modules.ModelList(
                _("Accounts and access"),
                models=("app.AppUser", "auth.Group"),
                column=1, order=3,
            ))
            self.children.append(modules.ModelList(
                _("Retention"),
                models=("app.RetentionPolicy", "app.PurgeRun"),
                column=1, order=5,
            ))

        # -- Students and guardians ------------------------------------
        if has(access.STUDENT):
            self.children.append(modules.LinkList(
                _("Start here"),
                children=[
                    {"title": _("My work — what to hand in"), "url": "/admin/my-work/"},
                ],
                column=0, order=0,
            ))
            self.children.append(modules.ModelList(
                _("My results"),
                models=("app.Submission", "app.TopicResult",
                        "app.AttendanceRecord"),
                column=0, order=1,
            ))
            self.children.append(modules.ModelList(
                _("My course"),
                models=("app.Lesson", "app.Syllabus", "app.Topic"),
                column=1, order=0,
            ))

        if has(access.GUARDIAN):
            self.children.append(modules.ModelList(
                _("My children"),
                models=("app.Student", "app.TopicResult",
                        "app.AttendanceRecord", "app.Evaluation"),
                column=0, order=0,
            ))

        if has(access.GUEST) and not (roles - {access.GUEST}):
            self.children.append(modules.ModelList(
                _("Curriculum"),
                models=("app.AcademyClass", "app.Subject"),
                column=0, order=0,
            ))

        # A signed-in user whose roles match nothing above still needs
        # something on the page rather than a blank one.
        if not self.children:
            self.children.append(modules.ModelList(
                _("Available to you"), exclude=("auth.*",), column=0, order=0,
            ))

        # Recent actions last, for everyone: it is the one panel that
        # answers "what did I just do?".
        self.children.append(modules.RecentActions(
            _("Recent actions"), 10, column=1, order=99,
        ))


class AcademyDashboard(_RolePanelsMixin, Dashboard):
    """The admin home page."""


class AcademyAppIndexDashboard(_RolePanelsMixin, AppIndexDashboard):
    """
    The page behind the "App" breadcrumb.

    Without this it shows Jet's default "Application models" list — every
    table in the app, alphabetically — which undoes the point of the home
    page. It shows the same role panels instead.
    """
