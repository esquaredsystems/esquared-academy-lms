"""
Roles, and what each one may see.

Two layers, because one is not enough:

  * **Model permissions** decide whether a role may touch a table at all.
    They live on Django groups, are seeded by `manage.py seed_roles`, and
    are enforced in the admin natively and in the API by `RolePermission`.

  * **Row scoping** decides *which* rows of a permitted table a person
    sees. Django permissions cannot express "their own" or "their ward's",
    so `scope_queryset` does, and every API list runs through it.

The roles:

    Admin                 everything
    Teaching Staff        curriculum, questions, papers, marking, registers,
                          and student profiles
    Non-academic Staff    attendance, and the student and grade lists it needs
    Student               their own record, results and attendance
    Guardian              read-only, and only for the students linked to them
    Guest                 read-only list of grades, subjects and topics
"""

from rest_framework.permissions import DjangoModelPermissions

ADMIN = "Admin"
TEACHING_STAFF = "Teaching Staff"
NON_ACADEMIC_STAFF = "Non-academic Staff"
STUDENT = "Student"
GUARDIAN = "Guardian"
GUEST = "Guest"

ROLES = [ADMIN, TEACHING_STAFF, NON_ACADEMIC_STAFF, STUDENT, GUARDIAN, GUEST]

#: Everything a Guest may read. Nothing else is visible to them at all.
GUEST_VISIBLE_MODELS = {"grade", "subject", "topic"}


class RolePermission(DjangoModelPermissions):
    """
    Django model permissions, with reads included.

    `DjangoModelPermissions` lets any authenticated user read anything it
    is applied to; that is wrong here, because Guest and Guardian are
    read-only roles whose whole definition is *which* reads they get. This
    subclass requires `view_<model>` for GET, HEAD and OPTIONS too.
    """

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


def role_names(user):
    if not user or not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


def has_role(user, *names):
    return bool(role_names(user) & set(names))


def is_unrestricted(user):
    """Staff roles see every row of the tables they may touch."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return has_role(user, ADMIN, TEACHING_STAFF, NON_ACADEMIC_STAFF)


def _student_for(user):
    from . import models

    return models.Student.objects.filter(user=user).first()


def _ward_ids(user):
    from . import models

    return list(
        models.GuardianLink.objects.filter(user=user).values_list("student_id", flat=True)
    )


def _scope_to_students(model_name, queryset, student_ids):
    """Narrow a queryset to rows belonging to a set of students."""
    paths = {
        "student": "id__in",
        "enrolment": "student_id__in",
        "studentsubject": "enrolment__student_id__in",
        "cohortmembership": "enrolment__student_id__in",
        "attempt": "student_id__in",
        "answer": "attempt__student_id__in",
        "evaluation": "answer__attempt__student_id__in",
        "attendancerecord": "enrolment__student_id__in",
        "guardianlink": "student_id__in",
    }
    lookup = paths.get(model_name)
    if lookup is None:
        return queryset.none()
    return queryset.filter(**{lookup: student_ids})


def scope_queryset(user, queryset):
    """
    Narrow `queryset` to what `user` is allowed to see.

    Called by every API list and detail lookup. Model permissions have
    already decided whether the table is reachable; this decides which of
    its rows are.
    """
    model_name = queryset.model._meta.model_name

    if is_unrestricted(user):
        return queryset

    if not user or not user.is_authenticated:
        return queryset.none()

    roles = role_names(user)

    if GUEST in roles and not (roles - {GUEST}):
        return queryset if model_name in GUEST_VISIBLE_MODELS else queryset.none()

    if STUDENT in roles:
        student = _student_for(user)
        if student is None:
            return queryset.none()
        if model_name in {"grade", "subject", "topic", "syllabus", "syllabustopic",
                          "questionpaper", "paperassignment", "attachment"}:
            return queryset
        return _scope_to_students(model_name, queryset, [student.id])

    if GUARDIAN in roles:
        wards = _ward_ids(user)
        if not wards:
            return queryset.none()
        if model_name in {"grade", "subject", "topic", "syllabus", "syllabustopic"}:
            return queryset
        return _scope_to_students(model_name, queryset, wards)

    return queryset.none()
