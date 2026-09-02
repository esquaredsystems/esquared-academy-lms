"""
Esquared Academy — assessment platform models.

Mirrors the published ERD (schema v2):

  * Grade and class are the same entity. Marks are never called "grade".
  * academic_year is a plain integer, not a foreign key.
  * Every table carries the audit block: created_by / date_created,
    changed_by / date_changed, voided / voided_by / date_voided /
    void_reason. Rows are voided, never deleted; purging is separate.
  * Unique constraints are partial (voided=False) so a voided row never
    blocks a corrected one.
  * paper_version and prompt_version are immutable once locked / active;
    paper_item pins the prompt version it will be marked by.
"""

import os
import uuid as uuid_lib

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from . import files
from .audit import get_current_user

USER = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------
# Enumerated domains
# ---------------------------------------------------------------------
class TextFormat(models.TextChoices):
    PLAIN = "plain", "Plain"
    HTML = "html", "HTML"
    MARKDOWN = "markdown", "Markdown"


class QuestionType(models.TextChoices):
    BINARY = "binary", "Binary (true/false)"
    NUMERIC = "numeric", "Numeric"
    TEXT = "text", "Text (AI marked)"


class ToleranceType(models.TextChoices):
    ABSOLUTE = "absolute", "Absolute"
    RELATIVE = "relative", "Relative (%)"
    GEOMETRIC = "geometric", "Geometric"


class SyllabusStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    RETIRED = "retired", "Retired"


class PromptStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class PaperPurpose(models.TextChoices):
    QUIZ = "quiz", "Quiz"
    ASSIGNMENT = "assignment", "Assignment"
    EXAM = "exam", "Exam"
    MOCK = "mock", "Mock"


class PaperStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    LOCKED = "locked", "Locked"
    RETIRED = "retired", "Retired"


class CohortPurpose(models.TextChoices):
    ACTIVITY = "activity", "Activity"
    INTEREST = "interest", "Interest"
    REMEDIAL = "remedial", "Remedial"
    OTHER = "other", "Other"


class MarkingMethod(models.TextChoices):
    HIGHEST = "highest", "Highest attempt"
    AVERAGE = "average", "Average of attempts"
    FIRST = "first", "First attempt"
    LAST = "last", "Last attempt"


class AttemptState(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    OVERDUE = "overdue", "Overdue"
    FINISHED = "finished", "Finished"
    ABANDONED = "abandoned", "Abandoned"


class EvalMethod(models.TextChoices):
    RULE = "rule", "Rule"
    AI = "ai", "AI"
    TEACHER = "teacher", "Teacher"


# ---------------------------------------------------------------------
# Audit block
# ---------------------------------------------------------------------
class ActiveManager(models.Manager):
    """Default manager: voided rows are invisible to every read path."""

    def get_queryset(self):
        return super().get_queryset().filter(voided=False)


class AuditModel(models.Model):
    """
    The audit block carried by every table in the schema.

    It is self-controlled. `uuid`, `created_by` and `date_created` are set
    once at insert and are restored from the database on every subsequent
    save, so nothing — admin, API or a careless script — can rewrite them.
    `changed_by` and `date_changed` are stamped automatically on update
    from the request user (see app/audit.py). The only audit fields a
    person may set are `voided` and `void_reason`, through `void()` or the
    admin.
    """

    #: Stable external identifier. Assigned at insert, never changes.
    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)

    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="+", null=True, blank=True,
        db_column="created_by",
    )
    date_created = models.DateTimeField(default=timezone.now, editable=False)
    changed_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="+", null=True, blank=True,
        db_column="changed_by",
    )
    date_changed = models.DateTimeField(null=True, blank=True, editable=False)
    voided = models.BooleanField(default=False, db_index=True)
    active_flag = models.BooleanField(
        default=True, null=True, editable=False,
        help_text=(
            "True while the row is live, NULL once voided. Unique constraints "
            "include this column so that voided rows stop competing for the "
            "key: NULLs are distinct in a unique index on every backend, "
            "which is how soft deletion stays portable to MySQL, where "
            "partial indexes do not exist."
        ),
    )
    voided_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="+", null=True, blank=True,
        db_column="voided_by",
    )
    date_voided = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    #: Set once at insert and restored on every later save.
    IMMUTABLE_AUDIT_FIELDS = ("uuid", "created_by_id", "date_created")

    def save(self, *args, **kwargs):
        actor = get_current_user()

        if self.pk:
            # Restore the write-once fields from the stored row, so an
            # attempt to change them is silently ignored rather than
            # trusted. One cheap query, values() only.
            stored = (
                type(self)
                .all_objects.filter(pk=self.pk)
                .values(*self.IMMUTABLE_AUDIT_FIELDS)
                .first()
            )
            if stored:
                for field, value in stored.items():
                    setattr(self, field, value)
            self.date_changed = timezone.now()
            if actor is not None:
                self.changed_by = actor
        else:
            if self.created_by_id is None and actor is not None:
                self.created_by = actor
            if not self.date_created:
                self.date_created = timezone.now()

        self.active_flag = None if self.voided else True

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "active_flag", "date_changed", "changed_by",
            }
        super().save(*args, **kwargs)

    def void(self, user=None, reason="", save=True):
        """
        Soft delete. The only supported way to remove a row, and — with
        `void_reason` — the only part of the audit block a person may set.
        """
        self.voided = True
        self.date_voided = timezone.now()
        self.voided_by = user or get_current_user()
        self.void_reason = reason or "voided"
        self.active_flag = None
        if save:
            self.save()
        return self

    def unvoid(self, user=None, save=True):
        self.voided = False
        self.date_voided = None
        self.voided_by = None
        self.void_reason = None
        self.active_flag = True
        self.changed_by = user or get_current_user()
        if save:
            self.save()
        return self

    @property
    def is_voided(self):
        return self.voided


def unique_active(fields, name):
    """
    Unique across live rows only.

    PostgreSQL would express this as a partial index
    (`condition=Q(voided=False)`), but MySQL has no partial indexes, so the
    constraint carries `active_flag` instead: True on a live row, NULL once
    voided. A unique index treats NULLs as distinct on MySQL, PostgreSQL and
    SQLite alike, so any number of voided rows may share a key while only
    one live row can hold it.
    """
    return models.UniqueConstraint(fields=[*fields, "active_flag"], name=name)


# ---------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------
class AppUser(AbstractUser, AuditModel):
    """
    Every audit column points here. AbstractUser already supplies username,
    first_name, last_name, email and last_login (the ERD's last_access);
    `suspended` is kept as an explicit column because it is an
    administrative state distinct from Django's is_active login flag.
    """

    id_number = models.CharField(max_length=64, null=True, blank=True)
    suspended = models.BooleanField(default=False)

    class Meta(AuditModel.Meta):
        db_table = "app_user"
        constraints = [
            unique_active(["id_number"], "app_user_id_number_uix"),
        ]

    def __str__(self):
        return self.get_full_name() or self.username


# ---------------------------------------------------------------------
# People & placement
# ---------------------------------------------------------------------
class Grade(AuditModel):
    """Grade and class are one entity: one class per grade."""

    level = models.IntegerField()
    short_name = models.CharField(max_length=32)
    full_name = models.CharField(max_length=128)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    is_terminal = models.BooleanField(
        default=False, help_text="The grade where subjects differ per student."
    )
    room = models.CharField(max_length=64, null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0, verbose_name="sort")
    visible = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "grade"
        ordering = ["sort_order", "level"]
        constraints = [
            unique_active(["level"], "grade_level_uix"),
            unique_active(["short_name"], "grade_short_name_uix"),
        ]

    def __str__(self):
        return self.full_name


class Student(AuditModel):
    user = models.OneToOneField(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="student_profile",
        help_text="Null if the student has no login.",
    )
    admission_no = models.CharField(max_length=64)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    date_of_birth = models.DateField(null=True, blank=True)
    guardian_name = models.CharField(max_length=128, null=True, blank=True)
    guardian_contact = models.CharField(max_length=128, null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "student"
        ordering = ["last_name", "first_name"]
        constraints = [
            unique_active(["admission_no"], "student_admission_uix"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_no})"


class Teacher(AuditModel):
    user = models.OneToOneField(
        USER, on_delete=models.PROTECT, related_name="teacher_profile"
    )
    staff_no = models.CharField(max_length=64)
    id_number = models.CharField(max_length=64, null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "teacher"
        constraints = [
            unique_active(["staff_no"], "teacher_staff_no_uix"),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.staff_no})"


class Enrolment(AuditModel):
    """One grade per student per year — the 'one grade at a time' rule."""

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrolments")
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="enrolments")
    academic_year = models.IntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    started_on = models.DateField(default=timezone.localdate)
    ended_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, default="active")

    class Meta(AuditModel.Meta):
        db_table = "enrolment"
        ordering = ["-academic_year", "grade"]
        indexes = [models.Index(fields=["grade", "academic_year"])]
        constraints = [
            unique_active(
                ["student", "academic_year"], "enrolment_one_grade_per_year_uix"
            ),
        ]

    def __str__(self):
        return f"{self.student} · {self.grade} · {self.academic_year}"


# ---------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------
class Subject(AuditModel):
    short_name = models.CharField(max_length=32)
    full_name = models.CharField(max_length=128)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    description_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")
    visible = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "subject"
        ordering = ["sort_order", "short_name"]
        constraints = [unique_active(["short_name"], "subject_short_name_uix")]

    def __str__(self):
        return self.full_name


class Topic(AuditModel):
    """
    Permanent catalogue. Dropping a topic from a year edits a syllabus.

    Topics nest. A syllabus section is a top-level topic and the things
    taught under it are its children — Programming holds Loops and
    Conditions; Rivers holds Erosion and Deposition. Questions can be
    written against any level, so a question can target the whole section
    or one idea inside it.

    `depth` and `path` are maintained by save() and let the tree be
    queried without recursion: every descendant of a topic has a path
    starting with that topic's path.
    """

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="topics")
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children",
        help_text="The topic this one sits under. Empty for a top-level syllabus section.",
    )
    depth = models.PositiveSmallIntegerField(
        default=0, editable=False, help_text="0 for a top-level topic, 1 for its children."
    )
    path = models.CharField(
        max_length=255, blank=True, default="", editable=False,
        help_text="Ancestor ids, root first, e.g. '4/17/23'. Descendants of a "
                  "topic all start with that topic's path.",
    )
    short_name = models.CharField(max_length=64)
    full_name = models.CharField(max_length=256)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    description_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")
    visible = models.BooleanField(default=True)
    attachments = GenericRelation("AttachmentLink", related_query_name="topic")

    class Meta(AuditModel.Meta):
        db_table = "topic"
        ordering = ["subject", "path", "sort_order"]
        indexes = [models.Index(fields=["parent"]), models.Index(fields=["path"])]
        constraints = [
            unique_active(["subject", "short_name"], "topic_short_name_uix")
        ]

    def __str__(self):
        return f"{self.subject.short_name} · {self.full_name}"

    # -- the tree ------------------------------------------------------
    MAX_DEPTH = 4

    def clean(self):
        """A parent must be a real ancestor candidate, not a relative."""
        super().clean()
        if not self.parent_id:
            return
        if self.parent_id == self.pk:
            raise ValidationError({"parent": "A topic cannot be its own parent."})
        if self.parent.subject_id != self.subject_id:
            raise ValidationError(
                {"parent": "The parent topic must belong to the same subject."}
            )
        if self.pk and str(self.pk) in (self.parent.path or "").split("/"):
            raise ValidationError(
                {"parent": "That topic is already below this one — the tree would loop."}
            )
        if self.parent.depth + 1 > self.MAX_DEPTH:
            raise ValidationError(
                {"parent": f"Topics nest at most {self.MAX_DEPTH} levels deep."}
            )

    def save(self, *args, **kwargs):
        # clean() is not called by save(); enforce the same rules here so
        # scripts and the API cannot build a broken tree either.
        if self.parent_id:
            self.full_clean_parent()
            self.depth = self.parent.depth + 1
        else:
            self.depth = 0
        super().save(*args, **kwargs)

        path = f"{self.parent.path}/{self.pk}" if self.parent_id else str(self.pk)
        if path != self.path:
            self.path = path
            super().save(update_fields=["path"])
            self._reparent_descendants()

    def full_clean_parent(self):
        from django.core.exceptions import ValidationError as _VE

        try:
            self.clean()
        except _VE as exc:
            raise ValueError("; ".join(sum(exc.message_dict.values(), [])))

    def _reparent_descendants(self):
        """Rewrite path and depth below this topic after it moves."""
        for child in Topic.all_objects.filter(parent=self):
            child.depth = self.depth + 1
            child.path = f"{self.path}/{child.pk}"
            super(Topic, child).save(update_fields=["depth", "path"])
            child._reparent_descendants()

    @property
    def is_root(self):
        return self.parent_id is None

    @property
    def full_path(self):
        """'Programming › Loops', for lists and pickers."""
        names = [t.full_name for t in self.ancestors()] + [self.full_name]
        return " › ".join(names)

    def ancestors(self):
        """Root first, this topic excluded."""
        ids = [int(part) for part in (self.path or "").split("/") if part]
        ids = [i for i in ids if i != self.pk]
        if not ids:
            return []
        by_id = {t.pk: t for t in Topic.objects.filter(pk__in=ids)}
        return [by_id[i] for i in ids if i in by_id]

    def descendants(self):
        """Every topic below this one, at any depth."""
        if not self.path:
            return Topic.objects.none()
        return Topic.objects.filter(path__startswith=f"{self.path}/")

    def subtree(self):
        """This topic and everything below it."""
        return Topic.objects.filter(models.Q(pk=self.pk) | models.Q(path__startswith=f"{self.path}/"))


class Syllabus(AuditModel):
    """One subject taught to one grade in one year, and its topic cohort."""

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="syllabi")
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="syllabi")
    academic_year = models.IntegerField()
    full_name = models.CharField(max_length=256, null=True, blank=True)
    is_core = models.BooleanField(
        default=True, help_text="Core subjects are taken by every student in the grade."
    )
    status = models.CharField(
        max_length=16, choices=SyllabusStatus.choices, default=SyllabusStatus.DRAFT
    )
    date_published = models.DateTimeField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "syllabus"
        verbose_name_plural = "syllabi"
        ordering = ["-academic_year", "grade", "subject"]
        constraints = [
            unique_active(
                ["subject", "grade", "academic_year"],
                "syllabus_subject_grade_year_uix",
            )
        ]

    def __str__(self):
        return f"{self.subject.short_name} · {self.grade.short_name} · {self.academic_year}"


class SyllabusTopic(AuditModel):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.PROTECT, related_name="topics")
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="syllabus_entries")
    sort_order = models.IntegerField(verbose_name="sort")
    weight_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta(AuditModel.Meta):
        db_table = "syllabus_topic"
        ordering = ["syllabus", "sort_order"]
        constraints = [
            unique_active(["syllabus", "topic"], "syllabus_topic_uix"),
            unique_active(["syllabus", "sort_order"], "syllabus_topic_order_uix"),
        ]

    def __str__(self):
        return f"{self.syllabus} · {self.topic.short_name}"


class StudentSubject(AuditModel):
    """Auto-filled from core syllabi; genuinely chosen in the terminal grade."""

    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT, related_name="subjects")
    syllabus = models.ForeignKey(Syllabus, on_delete=models.PROTECT, related_name="students")

    class Meta(AuditModel.Meta):
        db_table = "student_subject"
        constraints = [
            unique_active(["enrolment", "syllabus"], "student_subject_uix")
        ]

    def __str__(self):
        return f"{self.enrolment.student} · {self.syllabus.subject.short_name}"


class TeachingAssignment(AuditModel):
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="assignments")
    syllabus = models.ForeignKey(Syllabus, on_delete=models.PROTECT, related_name="teachers")
    role = models.CharField(max_length=32, default="primary")

    class Meta(AuditModel.Meta):
        db_table = "teaching_assignment"
        constraints = [
            unique_active(["teacher", "syllabus", "role"], "teaching_assignment_uix")
        ]

    def __str__(self):
        return f"{self.teacher} · {self.syllabus}"


# ---------------------------------------------------------------------
# Prompt library
# ---------------------------------------------------------------------
class EvaluationPrompt(AuditModel):
    """A reusable marking instruction shared by many questions."""

    name = models.CharField(max_length=128)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    description_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    applies_to = models.CharField(
        max_length=16, choices=QuestionType.choices, default=QuestionType.TEXT
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, null=True, blank=True,
        related_name="prompts", help_text="Null = usable for any subject.",
    )
    owner = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="owned_prompts"
    )
    visible = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "evaluation_prompt"
        ordering = ["name"]
        constraints = [unique_active(["name"], "evaluation_prompt_name_uix")]

    def __str__(self):
        return self.name


class PromptVersion(AuditModel):
    """Immutable once active. Rewording produces version_no + 1."""

    evaluation_prompt = models.ForeignKey(
        EvaluationPrompt, on_delete=models.PROTECT, related_name="versions"
    )
    version_no = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    prompt_text = models.TextField()
    prompt_text_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    rubric_json = models.JSONField(null=True, blank=True)
    required_variables = models.JSONField(
        default=list, blank=True,
        help_text="Question fields this prompt interpolates, e.g. ['mark_scheme'].",
    )
    model_hint = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=PromptStatus.choices, default=PromptStatus.DRAFT
    )
    effective_from = models.DateField(null=True, blank=True)
    stamp = models.CharField(max_length=64, null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "prompt_version"
        ordering = ["evaluation_prompt", "-version_no"]
        constraints = [
            unique_active(
                ["evaluation_prompt", "version_no"], "prompt_version_uix"
            )
        ]

    def __str__(self):
        return f"{self.evaluation_prompt.name} v{self.version_no}"


# ---------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------
class Question(AuditModel):
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="questions")
    name = models.CharField(max_length=256)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    question_text = models.TextField()
    question_text_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    general_feedback = models.TextField(null=True, blank=True)
    general_feedback_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    question_type = models.CharField(max_length=16, choices=QuestionType.choices)
    group = models.CharField(
        max_length=64, null=True, blank=True,
        help_text="Multi-part key, e.g. 'Q4'. Parts stay independently reusable.",
    )
    order_in_group = models.PositiveIntegerField(
        null=True, blank=True, help_text="1 = (a), 2 = (b)."
    )
    group_stem = models.TextField(null=True, blank=True, help_text="Shared preamble.")
    group_stem_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    default_mark = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    penalty = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    difficulty = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    media_url = models.URLField(null=True, blank=True)
    model_answer = models.TextField(null=True, blank=True)
    mark_scheme = models.TextField(null=True, blank=True)
    default_prompt_version = models.ForeignKey(
        PromptVersion, on_delete=models.PROTECT, null=True, blank=True,
        related_name="default_for_questions",
    )
    stamp = models.CharField(max_length=64, null=True, blank=True)
    visible = models.BooleanField(default=True)
    attachments = GenericRelation("AttachmentLink", related_query_name="question")

    class Meta(AuditModel.Meta):
        db_table = "question"
        ordering = ["topic", "group", "order_in_group", "id"]
        indexes = [models.Index(fields=["topic"]), models.Index(fields=["question_type"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(group__isnull=True, order_in_group__isnull=True)
                    | Q(group__isnull=False, order_in_group__isnull=False)
                ),
                name="question_group_paired",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(question_type=QuestionType.TEXT)
                    | Q(default_prompt_version__isnull=False)
                ),
                name="question_text_needs_prompt",
            ),
            unique_active(["group", "order_in_group"], "question_group_order_uix"),
        ]

    def __str__(self):
        return self.name


class BinaryConfig(AuditModel):
    question = models.OneToOneField(
        Question, on_delete=models.PROTECT, primary_key=True, related_name="binary_config"
    )
    expected_value = models.BooleanField()
    true_label = models.CharField(max_length=64, default="True")
    false_label = models.CharField(max_length=64, default="False")
    true_feedback = models.TextField(null=True, blank=True)
    false_feedback = models.TextField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "binary_config"

    def __str__(self):
        return f"{self.question} → {self.expected_value}"


class NumericConfig(AuditModel):
    question = models.OneToOneField(
        Question, on_delete=models.PROTECT, primary_key=True, related_name="numeric_config"
    )
    expected_value = models.DecimalField(max_digits=18, decimal_places=6)
    tolerance_type = models.CharField(
        max_length=16, choices=ToleranceType.choices, default=ToleranceType.ABSOLUTE
    )
    tolerance = models.DecimalField(
        max_digits=18, decimal_places=6, default=0, validators=[MinValueValidator(0)]
    )
    partial_band = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Wider band outside tolerance earning partial_fraction of the mark.",
    )
    partial_fraction = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    unit = models.CharField(max_length=32, null=True, blank=True)
    unit_penalty = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    significant_figures = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "numeric_config"

    def __str__(self):
        return f"{self.question} → {self.expected_value} ± {self.tolerance}"


# ---------------------------------------------------------------------
# Papers, versioning & delivery
# ---------------------------------------------------------------------
class QuestionPaper(AuditModel):
    """Stable identity only. It holds no questions; its versions do."""

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="papers")
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="papers")
    name = models.CharField(max_length=256)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    intro = models.TextField(null=True, blank=True)
    intro_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    purpose = models.CharField(
        max_length=16, choices=PaperPurpose.choices, default=PaperPurpose.QUIZ
    )
    owner = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="owned_papers"
    )
    attachments = GenericRelation("AttachmentLink", related_query_name="question_paper")

    class Meta(AuditModel.Meta):
        db_table = "question_paper"
        ordering = ["subject", "grade", "name"]

    def __str__(self):
        return f"{self.name} ({self.subject.short_name} · {self.grade.short_name})"


class PaperVersion(AuditModel):
    """
    The question cohort. Editable while draft; read-only once locked.
    A change to a locked version clones it into version_no + 1.
    """

    question_paper = models.ForeignKey(
        QuestionPaper, on_delete=models.PROTECT, related_name="versions"
    )
    version_no = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=16, choices=PaperStatus.choices, default=PaperStatus.DRAFT
    )
    date_locked = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="locked_papers"
    )
    cloned_from_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="clones"
    )
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "paper_version"
        ordering = ["question_paper", "-version_no"]
        constraints = [
            unique_active(["question_paper", "version_no"], "paper_version_uix"),
            models.CheckConstraint(
                condition=(
                    ~Q(status=PaperStatus.LOCKED)
                    | Q(date_locked__isnull=False, locked_by__isnull=False)
                ),
                name="paper_version_locked_fields",
            ),
        ]

    def __str__(self):
        return f"{self.question_paper.name} v{self.version_no} ({self.status})"

    @property
    def is_locked(self):
        return self.status == PaperStatus.LOCKED

    def lock(self, user):
        """Freeze the version and pin each text item's prompt version."""
        if self.is_locked:
            raise ValueError("Paper version is already locked.")
        for item in self.items.select_related("question"):
            if item.question.question_type == QuestionType.TEXT and not item.prompt_version_id:
                item.prompt_version = item.question.default_prompt_version
                item.save(update_fields=["prompt_version", "date_changed"])
        self.status = PaperStatus.LOCKED
        self.date_locked = timezone.now()
        self.locked_by = user
        self.total_marks = sum(i.max_mark for i in self.items.all()) or 0
        self.save()
        return self

    def clone(self, user):
        """Produce the next version, carrying the items across."""
        latest = (
            PaperVersion.all_objects.filter(question_paper=self.question_paper)
            .order_by("-version_no")
            .first()
        )
        new = PaperVersion.objects.create(
            question_paper=self.question_paper,
            version_no=latest.version_no + 1,
            status=PaperStatus.DRAFT,
            cloned_from_version=self,
            duration_minutes=self.duration_minutes,
            created_by=user,
        )
        for item in self.items.all():
            PaperItem.objects.create(
                paper_version=new,
                question=item.question,
                slot=item.slot,
                page=item.page,
                section_label=item.section_label,
                max_mark=item.max_mark,
                require_previous=item.require_previous,
                prompt_version=item.prompt_version,
                created_by=user,
            )
        return new


class PaperItem(AuditModel):
    paper_version = models.ForeignKey(
        PaperVersion, on_delete=models.PROTECT, related_name="items"
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="paper_items")
    slot = models.PositiveIntegerField(help_text="Position on the paper.")
    page = models.PositiveIntegerField(default=1)
    section_label = models.CharField(max_length=64, null=True, blank=True)
    max_mark = models.DecimalField(max_digits=6, decimal_places=2)
    require_previous = models.BooleanField(default=False)
    prompt_version = models.ForeignKey(
        PromptVersion, on_delete=models.PROTECT, null=True, blank=True,
        related_name="paper_items",
        help_text="Pinned at lock time; a re-versioned prompt never alters this paper.",
    )

    class Meta(AuditModel.Meta):
        db_table = "paper_item"
        ordering = ["paper_version", "slot"]
        constraints = [
            unique_active(["paper_version", "slot"], "paper_item_slot_uix")
        ]

    def __str__(self):
        return f"{self.paper_version} · slot {self.slot}"


class StudentCohort(AuditModel):
    """A group of students inside one grade — never across grades."""

    name = models.CharField(max_length=128)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    purpose = models.CharField(
        max_length=16, choices=CohortPurpose.choices, default=CohortPurpose.OTHER
    )
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="cohorts")
    academic_year = models.IntegerField()
    is_temporary = models.BooleanField(default=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "student_cohort"
        ordering = ["-academic_year", "grade", "name"]
        constraints = [
            unique_active(
                ["grade", "academic_year", "name"], "student_cohort_name_uix"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.grade.short_name} · {self.academic_year})"


class CohortMembership(AuditModel):
    student_cohort = models.ForeignKey(
        StudentCohort, on_delete=models.PROTECT, related_name="memberships"
    )
    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.PROTECT, related_name="cohort_memberships"
    )

    class Meta(AuditModel.Meta):
        db_table = "cohort_membership"
        constraints = [
            unique_active(
                ["student_cohort", "enrolment"], "cohort_membership_uix"
            )
        ]

    def __str__(self):
        return f"{self.enrolment.student} ∈ {self.student_cohort.name}"


class PaperAssignment(AuditModel):
    """Issues a locked version to a grade, or to one cohort inside it."""

    paper_version = models.ForeignKey(
        PaperVersion, on_delete=models.PROTECT, related_name="assignments"
    )
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="assignments")
    academic_year = models.IntegerField()
    student_cohort = models.ForeignKey(
        StudentCohort, on_delete=models.PROTECT, null=True, blank=True,
        related_name="assignments", help_text="Null = the whole grade.",
    )
    assigned_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="assignments_made"
    )
    time_open = models.DateTimeField(null=True, blank=True)
    time_close = models.DateTimeField(null=True, blank=True)
    time_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Seconds. Null = untimed."
    )
    attempts = models.PositiveIntegerField(default=0, help_text="0 = unlimited.")
    marking_method = models.CharField(
        max_length=16, choices=MarkingMethod.choices, default=MarkingMethod.HIGHEST
    )
    preferred_behaviour = models.CharField(max_length=32, default="deferred_feedback")
    shuffle_questions = models.BooleanField(default=False)
    is_practice = models.BooleanField(default=False)

    class Meta(AuditModel.Meta):
        db_table = "paper_assignment"
        ordering = ["-time_open", "id"]

    def __str__(self):
        target = self.student_cohort.name if self.student_cohort_id else self.grade.short_name
        return f"{self.paper_version} → {target}"


# ---------------------------------------------------------------------
# Assessment & marking
# ---------------------------------------------------------------------
class Attempt(AuditModel):
    paper_assignment = models.ForeignKey(
        PaperAssignment,
        on_delete=models.PROTECT,
        # not "attempts": PaperAssignment.attempts is the Moodle-style cap
        # on how many sittings are allowed (0 = unlimited).
        related_name="sittings",
    )
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="attempts")
    attempt_no = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    is_counted = models.BooleanField(
        default=True, help_text="Recomputed from the assignment's marking_method."
    )
    preview = models.BooleanField(default=False)
    time_start = models.DateTimeField(default=timezone.now)
    time_finish = models.DateTimeField(null=True, blank=True)
    state = models.CharField(
        max_length=16, choices=AttemptState.choices, default=AttemptState.IN_PROGRESS
    )
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    counted_flag = models.BooleanField(
        default=True, null=True, editable=False,
        help_text=(
            "True on the one attempt that counts toward the record, NULL "
            "otherwise. Keeps 'one counted attempt per student per "
            "assignment' enforceable without a partial index."
        ),
    )

    def save(self, *args, **kwargs):
        self.counted_flag = (
            True if (self.is_counted and not self.voided and not self.preview) else None
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"counted_flag"}
        super().save(*args, **kwargs)

    class Meta(AuditModel.Meta):
        db_table = "attempt"
        ordering = ["-time_start"]
        constraints = [
            unique_active(
                ["paper_assignment", "student", "attempt_no"], "attempt_uix"
            ),
            models.UniqueConstraint(
                fields=["paper_assignment", "student", "counted_flag"],
                name="attempt_one_counted_uix",
            ),
        ]

    def __str__(self):
        return f"{self.student} · {self.paper_assignment} · #{self.attempt_no}"


class Answer(AuditModel):
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT, related_name="answers")
    paper_item = models.ForeignKey(PaperItem, on_delete=models.PROTECT, related_name="answers")
    boolean_response = models.BooleanField(null=True, blank=True)
    numeric_response = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    text_response = models.TextField(null=True, blank=True)
    response_summary = models.TextField(null=True, blank=True)
    date_answered = models.DateTimeField(default=timezone.now)
    attachments = GenericRelation("AttachmentLink", related_query_name="answer")

    class Meta(AuditModel.Meta):
        db_table = "answer"
        ordering = ["attempt", "paper_item"]
        constraints = [unique_active(["attempt", "paper_item"], "answer_uix")]

    def __str__(self):
        return f"{self.attempt} · slot {self.paper_item.slot}"


class Evaluation(AuditModel):
    """
    Append-only. A teacher override inserts a new row pointing at
    `supersedes`; the AI's original marks and feedback are never lost.
    """

    answer = models.ForeignKey(Answer, on_delete=models.PROTECT, related_name="evaluations")
    method = models.CharField(max_length=16, choices=EvalMethod.choices)
    prompt_version = models.ForeignKey(
        PromptVersion, on_delete=models.PROTECT, null=True, blank=True,
        related_name="evaluations",
    )
    model_name = models.CharField(max_length=128, null=True, blank=True)
    awarded_marks = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(0)]
    )
    fraction = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    is_correct = models.BooleanField(null=True, blank=True)
    confidence = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    feedback = models.TextField(null=True, blank=True)
    feedback_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    evaluated_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="evaluations_made"
    )
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )

    class Meta(AuditModel.Meta):
        db_table = "evaluation"
        ordering = ["answer", "-date_created"]
        indexes = [models.Index(fields=["answer"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(method=EvalMethod.AI) | Q(prompt_version__isnull=False),
                name="evaluation_ai_needs_prompt",
            ),
            models.CheckConstraint(
                condition=~Q(method=EvalMethod.TEACHER) | Q(evaluated_by__isnull=False),
                name="evaluation_teacher_needs_marker",
            ),
        ]

    def __str__(self):
        return f"{self.answer} · {self.method} · {self.awarded_marks}"


# ---------------------------------------------------------------------
# Retention & purging
# ---------------------------------------------------------------------
class RetentionPolicy(AuditModel):
    """One row per table. purge_enabled stays false for assessment evidence."""

    target_table = models.CharField(max_length=64, unique=True)
    void_retention_days = models.PositiveIntegerField(default=365)
    purge_enabled = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "retention_policy"
        verbose_name_plural = "retention policies"
        ordering = ["target_table"]

    def __str__(self):
        return self.target_table


class PurgeRun(models.Model):
    """Immutable log. Carries no audit block and is never purged."""

    target_table = models.CharField(max_length=64)
    criteria = models.TextField(help_text="The predicate that selected the rows.")
    row_ids = models.JSONField(default=list)
    rows_purged = models.PositiveIntegerField()
    ran_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="purge_runs")
    date_run = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "purge_run"
        ordering = ["-date_run"]

    def __str__(self):
        return f"{self.target_table} · {self.rows_purged} rows · {self.date_run:%Y-%m-%d}"



# ---------------------------------------------------------------------
# Guardians
# ---------------------------------------------------------------------
class GuardianLink(AuditModel):
    """
    A guardian's login, tied to the students they may see.

    `student.guardian_name` and `guardian_contact` stay as the contact
    details on the student record. This is the access relationship: a
    guardian account sees exactly the students linked here and nothing
    else, enforced in app/access.py.
    """

    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="wards")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="guardians")
    relationship = models.CharField(
        max_length=32, default="guardian", help_text="father, mother, guardian, other."
    )
    is_primary = models.BooleanField(default=False)
    can_view_marks = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "guardian_link"
        constraints = [unique_active(["user", "student"], "guardian_link_uix")]

    def __str__(self):
        return f"{self.user} → {self.student} ({self.relationship})"


# ---------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------
class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    EXCUSED = "excused", "Excused absence"
    LEAVE = "leave", "Approved leave"


class AttendanceSession(AuditModel):
    """
    One register: a grade, on a date, for a period.

    `syllabus` is optional. Leave it empty for a day or homeroom register;
    set it to take attendance for one subject's lesson, which is what a
    teacher marking their own class needs.
    """

    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="attendance_sessions")
    academic_year = models.IntegerField()
    date = models.DateField(default=timezone.localdate)
    period = models.CharField(
        max_length=32, default="full_day",
        help_text="full_day, or a period label such as '1' or 'assembly'.",
    )
    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.PROTECT, null=True, blank=True,
        related_name="attendance_sessions",
        help_text="Set for a subject lesson; empty for a whole-day register.",
    )
    taken_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True, related_name="registers_taken"
    )
    is_finalised = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    syllabus_key = models.PositiveBigIntegerField(
        default=0, editable=False,
        help_text=(
            "syllabus_id, or 0 for a whole-day register. The unique key uses "
            "this instead of syllabus, because NULLs are distinct in a unique "
            "index — two day registers for the same date would not collide."
        ),
    )

    def save(self, *args, **kwargs):
        self.syllabus_key = self.syllabus_id or 0
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"syllabus_key"}
        super().save(*args, **kwargs)

    class Meta(AuditModel.Meta):
        db_table = "attendance_session"
        ordering = ["-date", "period"]
        indexes = [models.Index(fields=["grade", "date"]), models.Index(fields=["academic_year"])]
        constraints = [
            unique_active(
                ["grade", "academic_year", "date", "period", "syllabus_key"],
                "attendance_session_uix",
            )
        ]

    def __str__(self):
        subject = f" · {self.syllabus.subject.short_name}" if self.syllabus_id else ""
        return f"{self.grade.short_name} · {self.date}{subject} ({self.period})"

    @property
    def summary(self):
        """Counts by status, for the register header and reports."""
        counts = {}
        for record in self.records.all():
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts


class AttendanceRecord(AuditModel):
    """One student's mark in one register."""

    session = models.ForeignKey(
        AttendanceSession, on_delete=models.PROTECT, related_name="records"
    )
    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.PROTECT, related_name="attendance_records"
    )
    status = models.CharField(
        max_length=16, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT
    )
    minutes_late = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta(AuditModel.Meta):
        db_table = "attendance_record"
        ordering = ["session", "enrolment"]
        indexes = [models.Index(fields=["status"])]
        constraints = [unique_active(["session", "enrolment"], "attendance_record_uix")]

    def __str__(self):
        return f"{self.enrolment.student} · {self.session.date} · {self.get_status_display()}"

    @property
    def student(self):
        return self.enrolment.student

# ---------------------------------------------------------------------
# Attachments
#
# One root directory, a flat folder per kind, and a link table so any row
# in the system can carry files without every model growing its own
# columns. Uploads of any size arrive in chunks through UploadSession.
# ---------------------------------------------------------------------
class Attachment(AuditModel):
    """A stored file: image, PDF, audio, video or anything else."""

    file = models.FileField(upload_to=files.attachment_path, max_length=255)
    original_filename = models.CharField(max_length=255)
    kind = models.CharField(
        max_length=16, choices=files.FileKind.choices, default=files.FileKind.OTHER,
        help_text="Decided from the MIME type, with the extension as fallback.",
    )
    mime_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    checksum = models.CharField(
        max_length=64, blank=True, default="",
        help_text="SHA-256 of the contents. Re-uploading the same file reuses this row.",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    caption = models.TextField(blank=True, default="")
    #: Filled in for pictures and video where the values are known.
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "attachment"
        ordering = ["-date_created"]
        indexes = [models.Index(fields=["kind"]), models.Index(fields=["checksum"])]
        constraints = [unique_active(["checksum"], "attachment_checksum_uix")]

    def __str__(self):
        return self.title or self.original_filename

    @property
    def size_display(self):
        return files.human_size(self.size_bytes)

    def save(self, *args, **kwargs):
        if not self.kind or self.kind == files.FileKind.OTHER:
            self.kind = files.classify(self.mime_type, self.original_filename)
        super().save(*args, **kwargs)


class AttachmentLink(AuditModel):
    """
    Attaches a file to any row in the system — a question, an answer, a
    topic, a paper. `role` says what the file is for on that row, so a
    question can carry a figure and a mark-scheme scan at once.
    """

    attachment = models.ForeignKey(Attachment, on_delete=models.PROTECT, related_name="links")
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    role = models.CharField(
        max_length=32, default="attachment",
        help_text="e.g. figure, diagram, mark_scheme, submission, resource.",
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")

    class Meta(AuditModel.Meta):
        db_table = "attachment_link"
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        constraints = [
            unique_active(
                ["attachment", "content_type", "object_id", "role"],
                "attachment_link_uix",
            )
        ]

    def __str__(self):
        return f"{self.attachment} → {self.target} ({self.role})"


class UploadState(models.TextChoices):
    OPEN = "open", "Open"
    COMPLETED = "completed", "Completed"
    ABORTED = "aborted", "Aborted"


class UploadSession(AuditModel):
    """
    A large upload in progress.

    The browser slices the file and PUTs one chunk at a time; each chunk is
    appended to a part file under `_incoming/`. Nothing is held in memory
    and nothing needs the whole file in one request, so upload size is
    limited by disk rather than by the web server's body limit. `received`
    lets an interrupted upload resume where it stopped.
    """

    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=128, blank=True, default="")
    declared_size = models.BigIntegerField(default=0)
    received = models.BigIntegerField(default=0)
    state = models.CharField(max_length=16, choices=UploadState.choices, default=UploadState.OPEN)
    attachment = models.ForeignKey(
        Attachment, on_delete=models.PROTECT, null=True, blank=True, related_name="upload_sessions"
    )

    class Meta(AuditModel.Meta):
        db_table = "upload_session"
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.filename} ({self.received}/{self.declared_size})"

    @property
    def part_path(self):
        from django.conf import settings

        return os.path.join(settings.MEDIA_ROOT, "_incoming", f"{self.uuid}.part")

    def append(self, data, offset=None):
        """Append one chunk. `offset` guards against out-of-order chunks."""
        os.makedirs(os.path.dirname(self.part_path), exist_ok=True)
        if offset is not None and int(offset) != self.received:
            raise ValueError(
                f"Chunk starts at {offset} but {self.received} bytes are stored. "
                "Resume from the reported offset."
            )
        with open(self.part_path, "ab") as part:
            part.write(data)
        self.received = os.path.getsize(self.part_path)
        self.save(update_fields=["received"])
        return self.received

    def complete(self):
        """Turn the assembled part file into an Attachment."""
        from django.core.files import File

        if self.state != UploadState.OPEN:
            raise ValueError("This upload is already finished.")
        if not os.path.exists(self.part_path):
            raise ValueError("No chunks were received for this upload.")

        with open(self.part_path, "rb") as part:
            checksum = files.sha256_of(part)

            existing = Attachment.objects.filter(checksum=checksum).first()
            if existing:
                attachment = existing          # same bytes already stored
            else:
                attachment = Attachment(
                    original_filename=self.filename,
                    mime_type=self.mime_type,
                    kind=files.classify(self.mime_type, self.filename),
                    size_bytes=os.path.getsize(self.part_path),
                    checksum=checksum,
                    created_by=self.created_by,
                )
                attachment.file.save(self.filename, File(part), save=False)
                attachment.save()

        os.remove(self.part_path)
        self.attachment = attachment
        self.state = UploadState.COMPLETED
        self.save(update_fields=["attachment", "state"])
        return attachment

    def abort(self, reason="upload cancelled"):
        if os.path.exists(self.part_path):
            os.remove(self.part_path)
        self.state = UploadState.ABORTED
        self.save(update_fields=["state"])
        self.void(reason=reason)
        return self
