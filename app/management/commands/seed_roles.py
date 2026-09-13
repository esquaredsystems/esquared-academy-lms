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

CURRICULUM = ["academyclass", "subject", "topic", "syllabus", "syllabustopic"]
QUESTIONS = ["question", "questionattributetype", "questionattribute", "evaluationprompt", "promptversion"]
ATTENDANCE = ["attendancesession", "attendancerecord"]
FILES = ["attachment", "attachmentlink", "uploadsession"]
LESSONS = ["timetableslot", "lesson", "lessontopic", "lectureitem"]

#: role -> {model_name: actions}
ROLE_PERMISSIONS = {
    # Everything: permissions, passwords, academic authority, accounts and
    # office administration all live in one role now — see app/access.py's
    # module docstring for why the old finer-grained split was folded in.
    access.ADMINISTRATOR: "all",

    # Teaching and the pastoral side of it, plus composing questions and
    # drafting papers — the two used to be separate roles (Teaching Staff,
    # Paper Setter) but a teacher doing both was already the normal case.
    # Locking a paper or approving a lesson still needs Administrator —
    # see access.PAPER_APPROVAL_ROLES / access.may_approve_lessons — so a
    # teacher drafts and submits but never signs off on their own work.
    access.TEACHER: {
        "timetableslot": READ,
        "lesson": EDIT,
        "lessontopic": ALL,
        # Sets the work and marks what comes back.
        "handout": ALL,
        "handoutlesson": ALL,
        "submission": EDIT,
        "markline": EDIT,
        **{m: READ for m in CURRICULUM},
        **{m: ALL for m in ATTENDANCE},
        **{m: EDIT for m in FILES},
        # What their class is set, and how their students did on it —
        # but not the machinery behind it.
        "paperassignment": READ,
        "attempt": READ,
        "answer": READ,
        "evaluation": READ,
        "topicresult": EDIT,
        # Their students.
        "student": EDIT,
        "enrolment": EDIT,
        "studentsubject": EDIT,
        "studentcohort": ALL,
        "cohortmembership": ALL,
        "teachingassignment": READ,
        # Puts exam timetables and syllabi on the students' notice board.
        "notice": ALL,
        # The question bank and draft papers.
        **{m: ALL for m in QUESTIONS},
        "questionpaper": ALL,
        "paperversion": EDIT,
        "paperitem": ALL,
    },

    # Confirms or overrides what the grader proposed, and handles the
    # paper side of an exam sitting — scanning scripts and matching each
    # to the right student and paper. These used to be separate roles
    # (Marking Reviewer, Exam Operations); both are exam-administration
    # jobs blind to the question bank and to course content.
    # (The earlier attachment: EDIT was silently overwritten by a later
    # attachment: READ in the old Marking Reviewer dict, which had quietly
    # left the examiner unable to upload a checked file at all — the merge
    # here keeps the broader FILES: ALL instead.)
    access.EXAMINER: {
        "handoutsheet": READ,               # the sheet and answer scheme
        "submission": EDIT,                 # also what puts Checking in the menu
        "markline": EDIT,
        # Sees what the marking service proposed, and what it said about
        # its own confidence. Read-only: an examiner corrects a mark by
        # editing the mark line, which records them as its author, not by
        # editing the machine's record of what it originally said.
        "autogradejob": READ,
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

    # Students and guardians read; row scoping decides whose rows.
    access.STUDENT: {
        **{m: READ for m in LESSONS},
        "handout": READ,
        "handoutlesson": READ,
        "submission": ("view", "add"),   # handing work in writes a row
        "markline": READ,                # the marks breakdown, read only
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
        **{m: READ for m in LESSONS},
        "handout": READ,
        "submission": READ,
        "markline": READ,
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
