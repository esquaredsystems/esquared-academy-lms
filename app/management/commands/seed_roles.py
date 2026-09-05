"""
Create the roles and give each one its permissions.

    python manage.py seed_roles
    python manage.py seed_roles --dry-run

Roles are Django groups, so they work in the admin without any extra code,
and `app.access.RolePermission` applies the same permissions to the API.
Which *rows* a role sees is a separate question, answered by
`app.access.scope_queryset`.

Idempotent: permissions are set to exactly what is listed here, so a role
that has drifted is corrected rather than accumulating.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from app import access

ALL = ("view", "add", "change", "delete")
EDIT = ("view", "add", "change")
READ = ("view",)

CURRICULUM = ["grade", "subject", "topic", "syllabus", "syllabustopic"]
QUESTIONS = ["question", "binaryconfig", "numericconfig", "evaluationprompt", "promptversion"]
PAPERS = ["questionpaper", "paperversion", "paperitem", "paperassignment"]
MARKING = ["attempt", "answer", "evaluation", "topicresult"]
ATTENDANCE = ["attendancesession", "attendancerecord"]
FILES = ["attachment", "attachmentlink", "uploadsession"]
PEOPLE = ["student", "teacher", "enrolment", "studentsubject", "teachingassignment",
          "studentcohort", "cohortmembership", "guardianlink"]

#: role -> {model_name: actions}
ROLE_PERMISSIONS = {
    access.ADMIN: "all",

    # Everything a school runs on, but no control over who may do what.
    # Permissions and passwords belong to IT Administrator; both sit under
    # a superuser Owner login used sparingly.
    access.ACADEMIC_ADMIN: {
        **{m: ALL for m in CURRICULUM},
        **{m: ALL for m in QUESTIONS},
        **{m: ALL for m in PAPERS},
        **{m: ALL for m in MARKING},
        **{m: ALL for m in ATTENDANCE},
        **{m: ALL for m in FILES},
        **{m: ALL for m in PEOPLE},
        "retentionpolicy": READ,
        "purgerun": READ,
    },

    # Keeps the system running without seeing what is inside it. Accounts
    # and permissions are Django's own `auth` tables, granted in `handle`.
    access.IT_ADMIN: {
        "retentionpolicy": EDIT,
        "purgerun": READ,
        "uploadsession": READ,
    },

    # Academic authority. The one role that may lock a paper — see
    # `access.PAPER_APPROVAL_ROLES` and `may_approve_papers`.
    access.HEAD_OF_DEPARTMENT: {
        **{m: ALL for m in CURRICULUM},
        **{m: ALL for m in QUESTIONS},
        **{m: ALL for m in PAPERS},
        **{m: ALL for m in MARKING},
        **{m: READ for m in ATTENDANCE},
        **{m: EDIT for m in FILES},
        "student": READ,
        "teacher": READ,
        "enrolment": READ,
        "studentsubject": EDIT,
        "studentcohort": ALL,
        "cohortmembership": ALL,
        "teachingassignment": ALL,
        "guardianlink": READ,
    },

    # Teaching and the pastoral side of it. Paper setting and marking have
    # moved to the two roles below; a teacher who does those jobs is given
    # those roles as well.
    access.TEACHING_STAFF: {
        **{m: READ for m in CURRICULUM},
        **{m: ALL for m in ATTENDANCE},
        **{m: EDIT for m in FILES},
        "topicresult": EDIT,
        "attempt": READ,
        "answer": READ,
        "evaluation": READ,
        "question": READ,
        "questionpaper": READ,
        "paperversion": READ,
        "paperitem": READ,
        "paperassignment": READ,
        "student": EDIT,
        "enrolment": EDIT,
        "studentsubject": EDIT,
        "studentcohort": ALL,
        "cohortmembership": ALL,
        "teachingassignment": READ,
        "teacher": READ,
        "guardianlink": READ,
    },

    # Composes questions and drafts papers. No student data at all, so a
    # setter cannot see whose work their paper will be marked against.
    access.PAPER_SETTER: {
        **{m: READ for m in CURRICULUM},
        **{m: ALL for m in QUESTIONS},
        "questionpaper": ALL,
        "paperversion": EDIT,
        "paperitem": ALL,
        "attachment": EDIT,
        "attachmentlink": EDIT,
        "uploadsession": EDIT,
    },

    # Confirms or overrides what the grader proposed. Cannot touch the
    # paper or the questions, so a mark cannot be defended by rewriting
    # the question after the fact.
    access.MARKING_REVIEWER: {
        **{m: READ for m in CURRICULUM},
        **{m: READ for m in QUESTIONS},
        **{m: READ for m in PAPERS},
        **{m: EDIT for m in MARKING},
        "student": READ,
        "enrolment": READ,
        "studentsubject": READ,
        "attachment": READ,
        "attachmentlink": READ,
    },

    # Handles the paper, not the verdict: scans scripts and matches each
    # to the right student and paper. Deliberately blind to grades.
    access.EXAM_OPERATIONS: {
        **{m: READ for m in CURRICULUM},
        **{m: ALL for m in FILES},
        "questionpaper": READ,
        "paperversion": READ,
        "paperassignment": READ,
        "attempt": EDIT,
        "answer": EDIT,
        "student": READ,
        "enrolment": READ,
        "studentcohort": READ,
        "cohortmembership": READ,
    },

    access.NON_ACADEMIC_STAFF: {
        **{m: ALL for m in ATTENDANCE},
        "student": READ,
        "enrolment": READ,
        "grade": READ,
        "syllabus": READ,
        "studentcohort": READ,
        "cohortmembership": READ,
        "guardianlink": READ,
        "attachment": EDIT,
        "attachmentlink": EDIT,
        "uploadsession": EDIT,
    },

    # Students and guardians read; row scoping decides whose rows.
    access.STUDENT: {
        **{m: READ for m in CURRICULUM},
        "student": READ,
        "enrolment": READ,
        "studentsubject": READ,
        "paperassignment": READ,
        "attempt": ("view", "add", "change"),   # sitting a paper writes rows
        "answer": ("view", "add", "change"),
        "evaluation": READ,
        "topicresult": READ,
        "attendancerecord": READ,
        "attachment": READ,
        "attachmentlink": READ,
        "uploadsession": ("view", "add"),       # uploading a submission
    },

    access.GUARDIAN: {
        **{m: READ for m in CURRICULUM},
        "student": READ,
        "enrolment": READ,
        "studentsubject": READ,
        "attempt": READ,
        "answer": READ,
        "evaluation": READ,
        "topicresult": READ,
        "attendancerecord": READ,
        "attendancesession": READ,
        "guardianlink": READ,
    },

    access.GUEST: {m: READ for m in sorted(access.GUEST_VISIBLE_MODELS)},
}


class Command(BaseCommand):
    help = "Create every role in app.access.ROLES and set its permissions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        app_types = {
            ct.model: ct for ct in ContentType.objects.filter(app_label="app")
        }
        report = []

        try:
            with transaction.atomic():
                for role, spec in ROLE_PERMISSIONS.items():
                    group, created = Group.objects.get_or_create(name=role)
                    if spec == "all":
                        permissions = list(Permission.objects.filter(content_type__app_label="app"))
                        permissions += list(
                            Permission.objects.filter(content_type__app_label="auth")
                        )
                    elif role == access.IT_ADMIN:
                        # Accounts, groups and permissions live in Django's
                        # own `auth` app, plus the handful of app tables
                        # listed above. No student or assessment data.
                        codenames = [
                            f"{action}_{model}"
                            for model, actions in spec.items()
                            for action in actions
                            if model in app_types
                        ]
                        permissions = list(
                            Permission.objects.filter(
                                content_type__app_label="app", codename__in=codenames
                            )
                        )
                        permissions += list(
                            Permission.objects.filter(content_type__app_label="auth")
                        )
                        permissions += list(
                            Permission.objects.filter(
                                content_type__app_label="app", codename__in=["view_appuser", "add_appuser", "change_appuser"]
                            )
                        )
                    else:
                        codenames = [
                            f"{action}_{model}"
                            for model, actions in spec.items()
                            for action in actions
                            if model in app_types
                        ]
                        permissions = list(
                            Permission.objects.filter(
                                content_type__app_label="app", codename__in=codenames
                            )
                        )
                    group.permissions.set(permissions)
                    report.append((role, "created" if created else "updated", len(permissions)))
                if dry_run:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING("Dry run — nothing was written."))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Roles"))
        for role, state, count in report:
            self.stdout.write(f"  {role:22} {state:8} {count:4} permissions")
        self.stdout.write("")
        self.stdout.write(
            "Row-level scoping (a student's own rows, a guardian's wards) is applied "
            "by app/access.py, not by these permissions."
        )
        self.stdout.write("")


class _Rollback(Exception):
    pass
