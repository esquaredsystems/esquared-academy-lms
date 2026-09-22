"""Create and maintain the application's role groups and permissions."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
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

def ensure_roles():
    """Create every role and set its permissions exactly as defined above."""
    app_types = {
        ct.model: ct for ct in ContentType.objects.filter(app_label="app")
    }
    with transaction.atomic():
        for role, spec in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=role)
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
