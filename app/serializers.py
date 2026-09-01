"""
DRF serializers.

Every model in this app is a plain, fully-typed record: the API surface is
the same shape for all of them, so the serializers are built by a factory
that names each class properly (drf-spectacular uses the class name as the
OpenAPI component name) rather than repeating 27 identical class bodies.

Audit columns are read-only over the API. Rows are never deleted through
the API either — see `VoidSerializer` and the `void` action on the
viewsets.
"""

from rest_framework import serializers

from . import models

AUDIT_READ_ONLY = (
    "date_created",
    "date_changed",
    "voided",
    "date_voided",
    "void_reason",
    "created_by",
    "changed_by",
    "voided_by",
)


def build_serializer(model, name=None, depth=0):
    """Create a ModelSerializer class for `model` with audit fields locked."""
    read_only = tuple(
        f for f in AUDIT_READ_ONLY if hasattr(model, f) or f.endswith("_by")
    )

    meta = type(
        "Meta",
        (),
        {"model": model, "fields": "__all__", "read_only_fields": read_only, "depth": depth},
    )
    return type(
        name or f"{model.__name__}Serializer",
        (serializers.ModelSerializer,),
        {"Meta": meta},
    )


# --- identity ---------------------------------------------------------
class AppUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AppUser
        fields = (
            "id", "username", "first_name", "last_name", "email", "id_number",
            "suspended", "is_active", "is_staff", "last_login", "date_joined",
            "voided", "date_voided", "void_reason",
        )
        read_only_fields = ("last_login", "date_joined", "voided", "date_voided", "void_reason")


# --- people & placement ----------------------------------------------
GradeSerializer = build_serializer(models.Grade)
StudentSerializer = build_serializer(models.Student)
TeacherSerializer = build_serializer(models.Teacher)
EnrolmentSerializer = build_serializer(models.Enrolment)

# --- curriculum -------------------------------------------------------
SubjectSerializer = build_serializer(models.Subject)
TopicSerializer = build_serializer(models.Topic)
SyllabusSerializer = build_serializer(models.Syllabus)
SyllabusTopicSerializer = build_serializer(models.SyllabusTopic)
StudentSubjectSerializer = build_serializer(models.StudentSubject)
TeachingAssignmentSerializer = build_serializer(models.TeachingAssignment)

# --- prompt library ---------------------------------------------------
EvaluationPromptSerializer = build_serializer(models.EvaluationPrompt)
PromptVersionSerializer = build_serializer(models.PromptVersion)

# --- question bank ----------------------------------------------------
QuestionSerializer = build_serializer(models.Question)
BinaryConfigSerializer = build_serializer(models.BinaryConfig)
NumericConfigSerializer = build_serializer(models.NumericConfig)

# --- papers -----------------------------------------------------------
QuestionPaperSerializer = build_serializer(models.QuestionPaper)
PaperVersionSerializer = build_serializer(models.PaperVersion)
PaperItemSerializer = build_serializer(models.PaperItem)
StudentCohortSerializer = build_serializer(models.StudentCohort)
CohortMembershipSerializer = build_serializer(models.CohortMembership)
PaperAssignmentSerializer = build_serializer(models.PaperAssignment)

# --- assessment -------------------------------------------------------
AttemptSerializer = build_serializer(models.Attempt)
AnswerSerializer = build_serializer(models.Answer)
EvaluationSerializer = build_serializer(models.Evaluation)

# --- retention --------------------------------------------------------
RetentionPolicySerializer = build_serializer(models.RetentionPolicy)
PurgeRunSerializer = build_serializer(models.PurgeRun)


class PaperVersionDetailSerializer(serializers.ModelSerializer):
    """A paper version with its frozen items expanded."""

    items = PaperItemSerializer(many=True, read_only=True)

    class Meta:
        model = models.PaperVersion
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ("status", "date_locked", "locked_by")


class VoidSerializer(serializers.Serializer):
    """Payload for the `void` action: soft deletion needs a reason."""

    void_reason = serializers.CharField(
        max_length=500, help_text="Why this row is being voided. Recorded on the row."
    )


class LockSerializer(serializers.Serializer):
    """Payload for the `lock` action on a paper version."""

    confirm = serializers.BooleanField(
        default=True,
        help_text="Locking freezes the version and pins each text item's prompt version.",
    )
