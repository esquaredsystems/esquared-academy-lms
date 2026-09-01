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

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

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

    permission_classes = [IsAuthenticatedOrReadOnly]
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
        return qs

    def _user(self):
        user = getattr(self.request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def perform_create(self, serializer):
        serializer.save(created_by=self._user())

    def perform_update(self, serializer):
        serializer.save(changed_by=self._user(), date_changed=timezone.now())

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
