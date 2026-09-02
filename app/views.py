"""
REST API viewsets.

House rules, applied by `AuditedModelViewSet` to every resource:

  * Reads never return voided rows. `?include_voided=true` opts in, for
    audit screens.
  * DELETE does not delete. It voids the row, which requires a reason, so
    the destroy handler is replaced by the `void` action.
  * created_by / changed_by are stamped from the request user; the client
    cannot set them.
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import (
    FileUploadParser,
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from . import access
from . import files as app_files
from . import models, serializers

INCLUDE_VOIDED = OpenApiParameter(
    name="include_voided",
    type=bool,
    location=OpenApiParameter.QUERY,
    description="Include voided (soft-deleted) rows. Defaults to false.",
)


@extend_schema_view(
    list=extend_schema(parameters=[INCLUDE_VOIDED]),
    retrieve=extend_schema(parameters=[INCLUDE_VOIDED]),
)
class AuditedModelViewSet(viewsets.ModelViewSet):
    """Base viewset: soft deletion, audit stamping, voided-row filtering."""

    # Model permissions come from the role's group (manage.py seed_roles);
    # which rows the role then sees comes from access.scope_queryset.
    permission_classes = [IsAuthenticated, access.RolePermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    def get_queryset(self):
        model = self.serializer_class.Meta.model
        manager = model.all_objects if hasattr(model, "all_objects") else model.objects
        qs = manager.all()
        include_voided = str(
            self.request.query_params.get("include_voided", "")
        ).lower() in {"1", "true", "yes"}
        if not include_voided and hasattr(model, "voided"):
            qs = qs.filter(voided=False)
        return access.scope_queryset(getattr(self.request, "user", None), qs)

    def _user(self):
        user = getattr(self.request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def perform_create(self, serializer):
        # created_by and date_created are stamped by AuditModel.save() from
        # the request user; passing them here would be ignored anyway.
        serializer.save()

    def perform_update(self, serializer):
        # Likewise changed_by and date_changed.
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """DELETE voids the row. A reason may be supplied in the body."""
        instance = self.get_object()
        reason = request.data.get("void_reason") or "deleted via API"
        instance.void(user=self._user(), reason=reason)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=serializers.VoidSerializer,
        responses={200: None},
        description="Soft-delete this row, recording who voided it and why.",
    )
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        instance = self.get_object()
        payload = serializers.VoidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        instance.void(user=self._user(), reason=payload.validated_data["void_reason"])
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        request=None, responses={200: None}, description="Restore a voided row."
    )
    @action(detail=True, methods=["post"])
    def unvoid(self, request, pk=None):
        instance = self.get_object()
        instance.unvoid(user=self._user())
        return Response(self.get_serializer(instance).data)


# ---------------------------------------------------------------------
# People & placement
# ---------------------------------------------------------------------
class AppUserViewSet(AuditedModelViewSet):
    """Accounts. Every audit column on every table points at one of these."""

    serializer_class = serializers.AppUserSerializer
    filterset_fields = ["suspended", "is_active", "is_staff"]
    search_fields = ["username", "first_name", "last_name", "email", "id_number"]
    ordering_fields = ["username", "last_name", "date_joined"]


class GradeViewSet(AuditedModelViewSet):
    """Grades — which in this school are also the classes."""

    serializer_class = serializers.GradeSerializer
    filterset_fields = ["is_terminal", "visible", "level"]
    search_fields = ["short_name", "full_name", "id_number"]
    ordering_fields = ["sort_order", "level", "short_name"]


class StudentViewSet(AuditedModelViewSet):
    serializer_class = serializers.StudentSerializer
    filterset_fields = ["date_of_birth"]
    search_fields = ["first_name", "last_name", "admission_no", "id_number"]
    ordering_fields = ["last_name", "admission_no"]

    @extend_schema(
        responses=serializers.EnrolmentSerializer(many=True),
        description="Every enrolment for this student, newest year first.",
    )
    @action(detail=True, methods=["get"])
    def enrolments(self, request, pk=None):
        qs = models.Enrolment.objects.filter(student=self.get_object())
        return Response(serializers.EnrolmentSerializer(qs, many=True).data)


class TeacherViewSet(AuditedModelViewSet):
    """Teaching staff. One account per teacher."""

    serializer_class = serializers.TeacherSerializer
    search_fields = ["staff_no", "id_number", "user__first_name", "user__last_name"]


class EnrolmentViewSet(AuditedModelViewSet):
    """A student in one grade for one year. One per student per year."""

    serializer_class = serializers.EnrolmentSerializer
    filterset_fields = ["student", "grade", "academic_year", "status"]
    ordering_fields = ["academic_year", "started_on"]


# ---------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------
class SubjectViewSet(AuditedModelViewSet):
    serializer_class = serializers.SubjectSerializer
    filterset_fields = ["visible"]
    search_fields = ["short_name", "full_name", "id_number"]
    ordering_fields = ["sort_order", "short_name"]


class TopicViewSet(AuditedModelViewSet):
    """The permanent topic catalogue. Dropping a topic edits a syllabus."""

    serializer_class = serializers.TopicSerializer
    filterset_fields = ["subject", "visible"]
    search_fields = ["short_name", "full_name", "id_number"]
    ordering_fields = ["sort_order", "short_name"]


class SyllabusViewSet(AuditedModelViewSet):
    """One subject, one grade, one year — and that year's topic list."""

    serializer_class = serializers.SyllabusSerializer
    filterset_fields = ["subject", "grade", "academic_year", "status", "is_core"]
    ordering_fields = ["academic_year"]

    @extend_schema(
        responses=serializers.SyllabusTopicSerializer(many=True),
        description="The topics on this syllabus, in teaching order.",
    )
    @action(detail=True, methods=["get"])
    def topics(self, request, pk=None):
        qs = models.SyllabusTopic.objects.filter(syllabus=self.get_object())
        return Response(serializers.SyllabusTopicSerializer(qs, many=True).data)


class SyllabusTopicViewSet(AuditedModelViewSet):
    """A topic's membership of one year's syllabus, with its teaching order."""

    serializer_class = serializers.SyllabusTopicSerializer
    filterset_fields = ["syllabus", "topic"]
    ordering_fields = ["sort_order"]


class StudentSubjectViewSet(AuditedModelViewSet):
    """A student's subjects: automatic for core syllabi, chosen in the terminal grade."""

    serializer_class = serializers.StudentSubjectSerializer
    filterset_fields = ["enrolment", "syllabus"]


class TeachingAssignmentViewSet(AuditedModelViewSet):
    """Who teaches which syllabus."""

    serializer_class = serializers.TeachingAssignmentSerializer
    filterset_fields = ["teacher", "syllabus", "role"]


# ---------------------------------------------------------------------
# Prompt library
# ---------------------------------------------------------------------
class EvaluationPromptViewSet(AuditedModelViewSet):
    """Reusable marking instructions. One prompt serves many questions."""

    serializer_class = serializers.EvaluationPromptSerializer
    filterset_fields = ["applies_to", "subject", "visible"]
    search_fields = ["name", "description", "id_number"]


class PromptVersionViewSet(AuditedModelViewSet):
    """Immutable once active — a reworded prompt is a new version."""

    serializer_class = serializers.PromptVersionSerializer
    filterset_fields = ["evaluation_prompt", "status", "version_no"]
    search_fields = ["prompt_text"]
    ordering_fields = ["version_no", "effective_from"]

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.status == models.PromptStatus.ACTIVE:
            changed = {"prompt_text", "rubric_json"} & set(serializer.validated_data)
            if changed:
                raise ValidationError(
                    "An active prompt version cannot be reworded. Create a new version."
                )
        super().perform_update(serializer)


# ---------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------
class QuestionViewSet(AuditedModelViewSet):
    """
    The question bank. Questions are reused across papers rather than
    duplicated; `group` and `order_in_group` carry multi-part structure.
    """

    serializer_class = serializers.QuestionSerializer
    filterset_fields = ["topic", "question_type", "difficulty", "group", "visible"]
    search_fields = ["name", "question_text", "id_number", "group"]
    ordering_fields = ["name", "difficulty", "date_created"]

    @extend_schema(
        responses=serializers.QuestionSerializer(many=True),
        description="The other parts of this question's group, in order.",
    )
    @action(detail=True, methods=["get"])
    def group_parts(self, request, pk=None):
        question = self.get_object()
        if not question.group:
            return Response([])
        qs = models.Question.objects.filter(group=question.group).order_by("order_in_group")
        return Response(serializers.QuestionSerializer(qs, many=True).data)


class BinaryConfigViewSet(AuditedModelViewSet):
    """Answer key for true/false questions. All or nothing."""

    # These tables are keyed by their question, not by a separate id.
    lookup_field = "question_id"
    serializer_class = serializers.BinaryConfigSerializer
    filterset_fields = ["expected_value"]


class NumericConfigViewSet(AuditedModelViewSet):
    """Answer key for numeric questions, with the tolerance that counts as correct."""

    lookup_field = "question_id"
    serializer_class = serializers.NumericConfigSerializer
    filterset_fields = ["tolerance_type", "unit"]


# ---------------------------------------------------------------------
# Papers & versioning
# ---------------------------------------------------------------------
class QuestionPaperViewSet(AuditedModelViewSet):
    """The paper's stable identity. Its questions live on its versions."""

    serializer_class = serializers.QuestionPaperSerializer
    filterset_fields = ["subject", "grade", "purpose"]
    search_fields = ["name", "id_number"]


class PaperVersionViewSet(AuditedModelViewSet):
    """
    A frozen set of questions. Draft versions are editable; locking makes
    the version read-only and pins each text item's prompt version. To
    change a locked paper, clone it.
    """

    serializer_class = serializers.PaperVersionSerializer
    filterset_fields = ["question_paper", "status", "version_no"]
    ordering_fields = ["version_no", "date_locked"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.PaperVersionDetailSerializer
        return serializers.PaperVersionSerializer

    def perform_update(self, serializer):
        if self.get_object().is_locked:
            raise ValidationError(
                "A locked paper version is immutable. Clone it to make changes."
            )
        super().perform_update(serializer)

    @extend_schema(
        request=serializers.LockSerializer,
        responses=serializers.PaperVersionSerializer,
        description=(
            "Lock the version: freeze its items, pin each text question's prompt "
            "version, and total the marks."
        ),
    )
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        version = self.get_object()
        if version.is_locked:
            raise ValidationError("This version is already locked.")
        version.lock(user=self._user())
        return Response(serializers.PaperVersionSerializer(version).data)

    @extend_schema(
        request=None,
        responses=serializers.PaperVersionSerializer,
        description="Clone this version into the next version_no, carrying its items.",
    )
    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        new_version = self.get_object().clone(user=self._user())
        return Response(
            serializers.PaperVersionSerializer(new_version).data,
            status=status.HTTP_201_CREATED,
        )


class PaperItemViewSet(AuditedModelViewSet):
    """One question in one slot of one paper version. Frozen once locked."""

    serializer_class = serializers.PaperItemSerializer
    filterset_fields = ["paper_version", "question", "slot"]
    ordering_fields = ["slot", "page"]

    def perform_update(self, serializer):
        if self.get_object().paper_version.is_locked:
            raise ValidationError("Items on a locked paper version cannot be changed.")
        super().perform_update(serializer)


class StudentCohortViewSet(AuditedModelViewSet):
    """A group of students inside one grade — activity, interest, remedial."""

    serializer_class = serializers.StudentCohortSerializer
    filterset_fields = ["grade", "academic_year", "purpose", "is_temporary"]
    search_fields = ["name", "id_number"]

    @extend_schema(
        responses=serializers.CohortMembershipSerializer(many=True),
        description="Current members of this cohort.",
    )
    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        qs = models.CohortMembership.objects.filter(student_cohort=self.get_object())
        return Response(serializers.CohortMembershipSerializer(qs, many=True).data)


class CohortMembershipViewSet(AuditedModelViewSet):
    """A student's membership of a cohort, via their enrolment."""

    serializer_class = serializers.CohortMembershipSerializer
    filterset_fields = ["student_cohort", "enrolment"]


class PaperAssignmentViewSet(AuditedModelViewSet):
    """Issues a locked version to a grade, or to one cohort inside it."""

    serializer_class = serializers.PaperAssignmentSerializer
    filterset_fields = [
        "paper_version", "grade", "academic_year", "student_cohort",
        "is_practice", "marking_method",
    ]
    ordering_fields = ["time_open", "time_close"]


# ---------------------------------------------------------------------
# Assessment & marking
# ---------------------------------------------------------------------
class AttemptViewSet(AuditedModelViewSet):
    """One sitting. Repeat attempts are capped by the assignment."""

    serializer_class = serializers.AttemptSerializer
    filterset_fields = [
        "paper_assignment", "student", "state", "is_counted", "preview", "attempt_no",
    ]
    ordering_fields = ["time_start", "attempt_no", "total_marks"]

    @extend_schema(
        responses=serializers.AnswerSerializer(many=True),
        description="Every answer submitted in this attempt.",
    )
    @action(detail=True, methods=["get"])
    def answers(self, request, pk=None):
        qs = models.Answer.objects.filter(attempt=self.get_object())
        return Response(serializers.AnswerSerializer(qs, many=True).data)


class AnswerViewSet(AuditedModelViewSet):
    """A student's response to one item of a paper."""

    serializer_class = serializers.AnswerSerializer
    filterset_fields = ["attempt", "paper_item"]

    @extend_schema(
        responses=serializers.EvaluationSerializer(many=True),
        description="The marking history of this answer, newest first.",
    )
    @action(detail=True, methods=["get"])
    def evaluations(self, request, pk=None):
        qs = models.Evaluation.objects.filter(answer=self.get_object())
        return Response(serializers.EvaluationSerializer(qs, many=True).data)


class EvaluationViewSet(AuditedModelViewSet):
    """
    Append-only marking. A teacher override posts a new evaluation with
    `supersedes` set; the AI's original score is retained.
    """

    serializer_class = serializers.EvaluationSerializer
    filterset_fields = ["answer", "method", "prompt_version", "is_correct"]
    ordering_fields = ["date_created", "awarded_marks"]

    def perform_update(self, serializer):
        raise ValidationError(
            "Evaluations are append-only. Post a new evaluation with `supersedes` set."
        )


# ---------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------
class RetentionPolicyViewSet(AuditedModelViewSet):
    """Per-table retention. purge_enabled stays false for assessment evidence."""

    serializer_class = serializers.RetentionPolicySerializer
    filterset_fields = ["purge_enabled"]
    search_fields = ["target_table"]


class PurgeRunViewSet(viewsets.ReadOnlyModelViewSet):
    """The immutable purge log. Read-only, and never purged itself."""

    serializer_class = serializers.PurgeRunSerializer
    queryset = models.PurgeRun.objects.all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["target_table", "ran_by"]
    ordering_fields = ["date_run", "rows_purged"]


# ---------------------------------------------------------------------
# Attachments and uploads
# ---------------------------------------------------------------------
class AttachmentViewSet(AuditedModelViewSet):
    """
    Stored files. Every file lives under the media root in a flat folder
    for its kind — text, audio, video, picture, other.

    Small files can be POSTed here as multipart. Large ones go through
    /api/uploads/, which sends them in chunks.
    """

    serializer_class = serializers.AttachmentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["kind", "mime_type", "checksum"]
    search_fields = ["original_filename", "title", "caption"]
    ordering_fields = ["date_created", "size_bytes", "original_filename"]

    def create(self, request, *args, **kwargs):
        """Direct multipart upload, for files small enough for one request."""
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file was sent."})

        checksum = app_files.sha256_of(upload)
        existing = models.Attachment.objects.filter(checksum=checksum).first()
        if existing:
            # Same bytes already stored — hand back the row we have.
            return Response(
                self.get_serializer(existing).data, status=status.HTTP_200_OK
            )

        attachment = models.Attachment(
            original_filename=upload.name,
            mime_type=getattr(upload, "content_type", "") or "",
            kind=app_files.classify(getattr(upload, "content_type", ""), upload.name),
            size_bytes=upload.size,
            checksum=checksum,
            title=request.data.get("title", ""),
            caption=request.data.get("caption", ""),
        )
        attachment.file.save(upload.name, upload, save=False)
        attachment.save()
        return Response(
            self.get_serializer(attachment).data, status=status.HTTP_201_CREATED
        )


class AttachmentLinkViewSet(AuditedModelViewSet):
    """Attaches a file to a row — a question, an answer, a topic, a paper."""

    serializer_class = serializers.AttachmentLinkSerializer
    filterset_fields = ["attachment", "content_type", "object_id", "role"]
    ordering_fields = ["sort_order"]


@extend_schema_view(
    create=extend_schema(
        request=serializers.UploadInitSerializer,
        responses=serializers.UploadSessionSerializer,
        description=(
            "Start a chunked upload. Returns an upload id and the chunk size to "
            "send. Use this for large files: no single request carries the whole "
            "file, so size is bounded by disk rather than by the request limit."
        ),
    ),
)
class UploadSessionViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    Chunked uploads.

        POST /api/uploads/                     start, returns uuid + chunk_size
        PUT  /api/uploads/{uuid}/chunk/        raw bytes, X-Chunk-Offset header
        POST /api/uploads/{uuid}/complete/     assemble and store
        POST /api/uploads/{uuid}/abort/        discard what was received
        GET  /api/uploads/{uuid}/              how many bytes are stored, to resume
    """

    serializer_class = serializers.UploadSessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    queryset = models.UploadSession.objects.all()

    def create(self, request, *args, **kwargs):
        payload = serializers.UploadInitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        session = models.UploadSession.objects.create(
            filename=payload.validated_data["filename"],
            mime_type=payload.validated_data.get("mime_type", ""),
            declared_size=payload.validated_data.get("size_bytes", 0),
        )
        return Response(
            self.get_serializer(session).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=OpenApiTypes.BINARY,
        responses=serializers.UploadSessionSerializer,
        parameters=[
            OpenApiParameter(
                name="X-Chunk-Offset", type=int, location=OpenApiParameter.HEADER,
                description="Byte offset this chunk starts at. Must equal `received`.",
            )
        ],
        description="Append one chunk of the file. Send chunks in order.",
    )
    @action(detail=True, methods=["put"], parser_classes=[FileUploadParser])
    def chunk(self, request, uuid=None):
        session = self.get_object()
        if session.state != models.UploadState.OPEN:
            raise ValidationError("This upload is already finished.")

        data = request.data.get("file") if request.FILES else None
        raw = data.read() if data is not None else request.body
        if not raw:
            raise ValidationError("The chunk was empty.")

        offset = request.headers.get("X-Chunk-Offset")
        try:
            session.append(raw, offset=offset)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(self.get_serializer(session).data)

    @extend_schema(
        request=None,
        responses=serializers.AttachmentSerializer,
        description=(
            "Assemble the chunks into a stored file. If a file with the same "
            "SHA-256 already exists, that attachment is returned instead of a "
            "duplicate being written."
        ),
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, uuid=None):
        session = self.get_object()
        try:
            attachment = session.complete()
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(
            serializers.AttachmentSerializer(attachment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses={200: None}, description="Discard an upload in progress.")
    @action(detail=True, methods=["post"])
    def abort(self, request, uuid=None):
        session = self.get_object()
        session.abort()
        return Response(self.get_serializer(session).data)


# ---------------------------------------------------------------------
# Guardians and attendance
# ---------------------------------------------------------------------
class GuardianLinkViewSet(AuditedModelViewSet):
    """Which students a guardian account may see."""

    serializer_class = serializers.GuardianLinkSerializer
    filterset_fields = ["user", "student", "relationship", "is_primary"]
    search_fields = ["student__first_name", "student__last_name", "user__username"]


class AttendanceSessionViewSet(AuditedModelViewSet):
    """
    A register: one grade, one date, one period. Leave `syllabus` empty for
    a whole-day register, or set it to take attendance for one lesson.
    """

    serializer_class = serializers.AttendanceSessionSerializer
    filterset_fields = ["grade", "academic_year", "date", "period", "syllabus", "is_finalised"]
    ordering_fields = ["date", "period"]

    @extend_schema(
        request=serializers.AttendanceMarkSerializer,
        responses=serializers.AttendanceRecordSerializer(many=True),
        description=(
            "Mark the whole register in one call. Any enrolment not named is "
            "recorded as present, so a teacher only sends the exceptions."
        ),
    )
    @action(detail=True, methods=["post"])
    def mark(self, request, pk=None):
        session = self.get_object()
        payload = serializers.AttendanceMarkSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        marks = {entry["enrolment"]: entry for entry in payload.validated_data["records"]}
        default = payload.validated_data["default_status"]

        enrolments = models.Enrolment.objects.filter(
            grade=session.grade, academic_year=session.academic_year
        )
        written = []
        for enrolment in enrolments:
            entry = marks.get(enrolment.id, {})
            record = models.AttendanceRecord.objects.filter(
                session=session, enrolment=enrolment
            ).first()
            values = {
                "status": entry.get("status", default),
                "minutes_late": entry.get("minutes_late"),
                "note": entry.get("note", ""),
            }
            if record:
                for field, value in values.items():
                    setattr(record, field, value)
                record.save()
            else:
                record = models.AttendanceRecord.objects.create(
                    session=session, enrolment=enrolment, **values
                )
            written.append(record)

        return Response(serializers.AttendanceRecordSerializer(written, many=True).data)

    @extend_schema(
        responses=serializers.AttendanceRecordSerializer(many=True),
        description="The marks in this register.",
    )
    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        qs = models.AttendanceRecord.objects.filter(session=self.get_object())
        return Response(serializers.AttendanceRecordSerializer(qs, many=True).data)


class AttendanceRecordViewSet(AuditedModelViewSet):
    """One student's mark in one register."""

    serializer_class = serializers.AttendanceRecordSerializer
    filterset_fields = ["session", "enrolment", "status"]
    ordering_fields = ["session__date"]
