"""
E Squared Academy — assessment platform models.

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

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

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
    """The eight audit columns carried by every table in the schema."""

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

    def save(self, *args, **kwargs):
        if self.pk:
            self.date_changed = timezone.now()
        self.active_flag = None if self.voided else True
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"active_flag"}
        super().save(*args, **kwargs)

    def void(self, user=None, reason="", save=True):
        """Soft delete. The only supported way to remove a row."""
        self.voided = True
        self.date_voided = timezone.now()
        self.voided_by = user
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
        self.changed_by = user
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
    sort_order = models.IntegerField(default=0)
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
    sort_order = models.IntegerField(default=0)
    visible = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "subject"
        ordering = ["sort_order", "short_name"]
        constraints = [unique_active(["short_name"], "subject_short_name_uix")]

    def __str__(self):
        return self.full_name


class Topic(AuditModel):
    """Permanent catalogue. Dropping a topic from a year edits a syllabus."""

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="topics")
    short_name = models.CharField(max_length=64)
    full_name = models.CharField(max_length=256)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    description_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    sort_order = models.IntegerField(default=0)
    visible = models.BooleanField(default=True)

    class Meta(AuditModel.Meta):
        db_table = "topic"
        ordering = ["subject", "sort_order"]
        constraints = [
            unique_active(["subject", "short_name"], "topic_short_name_uix")
        ]

    def __str__(self):
        return f"{self.subject.short_name} · {self.full_name}"


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
    sort_order = models.IntegerField()
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
