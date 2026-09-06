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

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import models

# The audit block is self-controlled: the API may never write these.
AUDIT_READ_ONLY = (
    "uuid",
    "created_by",
    "date_created",
    "changed_by",
    "date_changed",
    "voided_by",
    "date_voided",
)

# The two exceptions: voiding is a decision a person makes, and it needs a
# reason. Everything else about the audit block stamps itself.
AUDIT_WRITABLE = ("voided", "void_reason")


def build_serializer(model, name=None, depth=0):
    """Create a ModelSerializer class for `model` with audit fields locked."""
    read_only = AUDIT_READ_ONLY

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
            "id", "uuid", "username", "first_name", "last_name", "email", "id_number",
            "suspended", "is_active", "is_staff", "last_login", "date_joined",
            "voided", "void_reason", "date_voided",
        )
        read_only_fields = ("uuid", "last_login", "date_joined", "date_voided")


# --- people & placement ----------------------------------------------
GradeSerializer = build_serializer(models.Grade)
StudentSerializer = build_serializer(models.Student)
TeacherSerializer = build_serializer(models.Teacher)
EnrolmentSerializer = build_serializer(models.Enrolment)

# --- curriculum -------------------------------------------------------
SubjectSerializer = build_serializer(models.Subject)
class TopicSerializer(serializers.ModelSerializer):
    """Topics nest; `full_path` and `child_count` save the client a walk."""

    full_path = serializers.CharField(read_only=True)
    child_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Topic
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ("depth", "path")

    @extend_schema_field(serializers.IntegerField())
    def get_child_count(self, obj):
        return obj.children.count()
SyllabusSerializer = build_serializer(models.Syllabus)
SyllabusTopicSerializer = build_serializer(models.SyllabusTopic)
StudentSubjectSerializer = build_serializer(models.StudentSubject)
TopicResultSerializer = build_serializer(models.TopicResult)
TeachingAssignmentSerializer = build_serializer(models.TeachingAssignment)

# --- timetable and lessons -------------------------------------------
TimetableSlotSerializer = build_serializer(models.TimetableSlot)
#: `status` and the review stamps stay writable here for the admin's
#: sake, but the API's own workflow goes through the submit / approve /
#: return actions on LessonViewSet, which record who did it.
LessonSerializer = build_serializer(models.Lesson)
LessonTopicSerializer = build_serializer(models.LessonTopic)
LectureItemSerializer = build_serializer(models.LectureItem)

# --- handouts and submissions ----------------------------------------
HandoutSerializer = build_serializer(models.Handout)
HandoutLessonSerializer = build_serializer(models.HandoutLesson)
SubmissionSerializer = build_serializer(models.Submission)
HandoutExtensionSerializer = build_serializer(models.HandoutExtension)
HandoutSheetSerializer = build_serializer(models.HandoutSheet)

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


class TopicTreeSerializer(serializers.Serializer):
    """One node of the knowledge graph. `children` holds the same shape."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    short_name = serializers.CharField()
    type = serializers.ChoiceField(choices=["subject", "topic"])
    depth = serializers.IntegerField()
    question_count = serializers.IntegerField(allow_null=True)
    admin_url = serializers.CharField()
    children = serializers.ListField(child=serializers.DictField(), required=False)


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


# --- attachments ------------------------------------------------------
class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    size_display = serializers.CharField(read_only=True)

    class Meta:
        model = models.Attachment
        fields = (
            "id", "uuid", "url", "file", "original_filename", "kind", "mime_type",
            "size_bytes", "size_display", "checksum", "title", "caption",
            "width", "height", "duration_seconds",
            "voided", "void_reason", "date_created", "created_by",
        )
        read_only_fields = (
            "uuid", "file", "original_filename", "kind", "mime_type", "size_bytes",
            "checksum", "date_created", "created_by",
        )

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url


class AttachmentLinkSerializer(serializers.ModelSerializer):
    attachment_detail = AttachmentSerializer(source="attachment", read_only=True)
    content_type_name = serializers.SerializerMethodField()

    class Meta:
        model = models.AttachmentLink
        fields = (
            "id", "uuid", "attachment", "attachment_detail", "content_type",
            "content_type_name", "object_id", "role", "sort_order",
            "voided", "void_reason",
        )
        read_only_fields = ("uuid",)

    @extend_schema_field(serializers.CharField())
    def get_content_type_name(self, obj):
        return f"{obj.content_type.app_label}.{obj.content_type.model}"


class UploadInitSerializer(serializers.Serializer):
    """Starts a chunked upload."""

    filename = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=128, required=False, allow_blank=True)
    size_bytes = serializers.IntegerField(min_value=0, required=False, default=0)


class UploadSessionSerializer(serializers.ModelSerializer):
    attachment_detail = AttachmentSerializer(source="attachment", read_only=True)
    chunk_size = serializers.SerializerMethodField()

    class Meta:
        model = models.UploadSession
        fields = (
            "uuid", "filename", "mime_type", "declared_size", "received",
            "state", "chunk_size", "attachment", "attachment_detail",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_chunk_size(self, obj):
        from django.conf import settings

        return settings.UPLOAD_CHUNK_SIZE


# --- guardians and attendance ----------------------------------------
GuardianLinkSerializer = build_serializer(models.GuardianLink)
AttendanceSessionSerializer = build_serializer(models.AttendanceSession)


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = models.AttendanceRecord
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY

    @extend_schema_field(serializers.CharField())
    def get_student_name(self, obj):
        student = obj.enrolment.student
        return f"{student.first_name} {student.last_name}"


class AttendanceEntrySerializer(serializers.Serializer):
    enrolment = serializers.IntegerField()
    status = serializers.ChoiceField(choices=models.AttendanceStatus.choices)
    minutes_late = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class AttendanceMarkSerializer(serializers.Serializer):
    """Mark a whole register: send the exceptions, not the whole class."""

    default_status = serializers.ChoiceField(
        choices=models.AttendanceStatus.choices,
        default=models.AttendanceStatus.PRESENT,
        help_text="Applied to every enrolment not named in `records`.",
    )
    records = AttendanceEntrySerializer(many=True, required=False, default=list)
