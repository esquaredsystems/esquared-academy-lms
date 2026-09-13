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
from datetime import datetime, time as datetime_time
from decimal import Decimal

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


class LessonStatus(models.TextChoices):
    """
    A lesson's place in the review workflow.

    A teacher drafts and submits; a Head of Department approves or sends
    it back. Only an approved lesson is course content, and only approved
    material reaches students.
    """

    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted for review"
    APPROVED = "approved", "Approved"
    RETURNED = "returned", "Returned for changes"
    RETIRED = "retired", "Retired"


class HandoutStatus(models.TextChoices):
    """
    A handout's life.

    DRAFT while it is being written, ACTIVE once the teacher hands it out
    — which is also the moment it appears in the students' accounts —
    and CLOSED when submissions are no longer accepted.
    """

    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    CLOSED = "closed", "Closed"
    RETIRED = "retired", "Retired"


class SubmissionState(models.TextChoices):
    """
    The life of one handed-in piece, from the desk it lands on next.

    A student's work is checked by the examiner, then the mark is held for
    the class teacher to approve — nothing reaches the student until the
    teacher has signed it off. The teacher may instead send it back to the
    examiner to re-check, or ask the student to do the work again.
    """

    SUBMITTED = "submitted", "Waiting for the examiner"
    GRADING = "grading", "Being marked"
    MARKED = "marked", "Checked — waiting for teacher approval"
    SENT_BACK = "sent_back", "Sent back to the examiner"
    APPROVED = "approved", "Approved — released to the student"
    RETURNED = "returned", "Sent back to the student to redo"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected — unreadable"


class TimerStatus(models.TextChoices):
    """Where the class clock is, said plainly rather than deduced."""

    IDLE = "idle", "Not started"
    RUNNING = "running", "Running"
    PAUSED = "paused", "Paused"
    ENDED = "ended", "Ended"


class DayOfWeek(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


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


class NationalIdType(models.TextChoices):
    """Which document a student's national_id came from."""

    CNIC = "cnic", "CNIC"
    B_FORM = "b_form", "B-Form"
    PASSPORT = "passport", "Passport"


class HandoutKind(models.TextChoices):
    """
    What kind of paper this is, which decides how it travels.

    An ASSIGNMENT is set in class and handed back by the student; the
    other three are sat under supervision. The difference matters in two
    places: an exam paper is never shown to a class before it is sat, and
    exam marks are aggregated separately from coursework, because mixing
    them is a school policy decision rather than an arithmetic one.
    """

    ASSIGNMENT = "assignment", "Assignment"
    ASSESSMENT = "assessment", "Class assessment"
    MOCK = "mock", "Mock exam"
    QUARTERLY = "quarterly", "Quarterly exam"


class MarkSource(models.TextChoices):
    """
    Who put this mark here.

    Every line records its own origin, so an overridden auto-mark still
    shows what the marker originally said. AUTO is written by the
    autograding service; a human editing a line takes ownership of it.
    """

    AUTO = "auto", "Autograder"
    EXAMINER = "examiner", "Examiner"
    TEACHER = "teacher", "Teacher"


class TopicImportance(models.IntegerChoices):
    """
    How much a topic counts toward the subject mark.

    Set once, on the syllabus, where it is a curriculum judgement rather
    than something decided under time pressure the night an assignment is
    written. Three levels, because six teachers will not apply a finer
    scale consistently across a year, and inconsistent weights are worse
    than none.

    Stored as `SyllabusTopic.weight_pct`; only the ratios are ever used,
    so a school that would rather allocate a true percentage across its
    topics can do that instead and the arithmetic is unchanged.
    """

    SUPPORTING = 30, "Supporting"
    STANDARD = 60, "Standard"
    CORE = 100, "Core"


class NoticeCategory(models.TextChoices):
    EXAM_TIMETABLE = "exam_timetable", "Exam timetable"
    EXAM_SYLLABUS = "exam_syllabus", "Exam syllabus"
    GENERAL = "general", "General notice"


class AutogradeStatus(models.TextChoices):
    """Where one autograding request has got to."""

    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class SubjectStatus(models.TextChoices):
    """
    Where a student stands with one subject, for the knowledge map.

    There is no per-subject result in the schema yet, so "passed" means
    the student carried the subject through an enrolment that has since
    finished — the year ended, or the enrolment was closed. When marks
    arrive, this is the one place that has to change.
    """

    STUDYING = "studying", "Currently studying"
    PASSED = "passed", "Passed"
    NOT_TAKEN = "not_taken", "Never taken"


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
    first_name = models.CharField(
        max_length=128,
        help_text="As printed on the national ID. Many names do not split, "
                  "so everything but the final word belongs here.",
    )
    last_name = models.CharField(
        max_length=128, blank=True, default="",
        help_text="Optional — leave empty when the ID carries a single name.",
    )
    date_of_birth = models.DateField(null=True, blank=True)

    # Contact. Optional at admission and filled in later; all of it is
    # required to enter a candidate for a Cambridge examination.
    email = models.EmailField(
        max_length=254, null=True, blank=True, default=None,
        help_text="Unique to this student — two students may not share one. "
                  "Optional at admission; required before an exam entry. "
                  "Stored as empty (NULL) when not yet known.",
    )
    mobile = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Mobile number, with country code for an overseas number.",
    )
    address = models.TextField(
        blank=True, default="",
        help_text="Residential address, as it should appear on an exam entry.",
    )

    # Identity documents.
    national_id = models.CharField(
        max_length=64, null=True, blank=True, default=None,
        help_text="CNIC, B-Form or passport number, exactly as printed. "
                  "Unique — no two students may share one. Optional at "
                  "admission; required before an exam entry.",
    )
    national_id_type = models.CharField(
        max_length=16, choices=NationalIdType.choices, blank=True, default="",
        help_text="Which document national_id came from.",
    )

    guardian_name = models.CharField(max_length=128, null=True, blank=True)
    guardian_contact = models.CharField(max_length=128, null=True, blank=True)
    guardian_contact_2 = models.CharField(
        max_length=128, blank=True, default="",
        help_text="A second number for the guardian. Cambridge asks for two "
                  "for candidates under 18.",
    )
    photo = models.ImageField(
        upload_to=files.person_photo_path, null=True, blank=True,
        max_length=256, validators=[files.validate_person_photo],
        help_text=files.PHOTO_HELP,
    )

    class Meta(AuditModel.Meta):
        db_table = "student"
        ordering = ["last_name", "first_name"]
        constraints = [
            unique_active(["admission_no"], "student_admission_uix"),
            # A blank email is stored as NULL, and MySQL treats NULLs as
            # distinct, so any number of students may have no email while
            # no two live students may share the same one.
            unique_active(["email"], "student_email_uix"),
            unique_active(["national_id"], "student_national_id_uix"),
        ]

    #: Blank means "not known yet", which must not collide under the unique
    #: indexes above. Django's admin submits an empty string, so it is
    #: turned into NULL on the way in.
    NULL_WHEN_BLANK = ("email", "national_id")

    def save(self, *args, **kwargs):
        for field in self.NULL_WHEN_BLANK:
            if not (getattr(self, field) or "").strip():
                setattr(self, field, None)
            else:
                setattr(self, field, getattr(self, field).strip())
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.admission_no})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def subject_records(self, year=None):
        """
        {subject id: record} — one record per subject ever taken.

        A subject taken more than once (repeated, or continued into the
        next grade) keeps the record worth showing: the year in progress
        if there is one, otherwise the most recent finished year. Each
        record carries the StudentSubject row itself, so the caller can
        read its topic results without going back to the database.
        """
        year = year or timezone.localdate().year
        rows = (
            StudentSubject.objects
            .filter(enrolment__student=self, enrolment__voided=False, voided=False)
            .select_related("enrolment", "syllabus", "syllabus__subject")
        )

        best = {}
        for row in rows:
            enrolment = row.enrolment
            finished = bool(enrolment.ended_on) or enrolment.academic_year < year
            record = {
                "student_subject": row,
                "syllabus": row.syllabus,
                "year": enrolment.academic_year,
                "status": SubjectStatus.PASSED if finished else SubjectStatus.STUDYING,
            }
            held = best.get(row.syllabus.subject_id)
            if held is None or self._outranks(record, held):
                best[row.syllabus.subject_id] = record
        return best

    @staticmethod
    def _outranks(candidate, held):
        """A year in progress beats a finished one; then the later year."""
        studying = SubjectStatus.STUDYING
        if (candidate["status"] == studying) != (held["status"] == studying):
            return candidate["status"] == studying
        return candidate["year"] > held["year"]

    def subject_history(self, year=None):
        """{subject id: SubjectStatus}, the summary of subject_records."""
        return {
            subject_id: record["status"]
            for subject_id, record in self.subject_records(year=year).items()
        }


class Teacher(AuditModel):
    user = models.OneToOneField(
        USER, on_delete=models.PROTECT, related_name="teacher_profile"
    )
    staff_no = models.CharField(max_length=64)
    id_number = models.CharField(max_length=64, null=True, blank=True)
    photo = models.ImageField(
        upload_to=files.person_photo_path, null=True, blank=True,
        max_length=256, validators=[files.validate_person_photo],
        help_text=files.PHOTO_HELP,
    )

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

    def teaching_summary(self, syllabus=None):
        """
        How much teaching this topic has actually taken.

        Counts the lessons it appeared in and sums their clock. Both are
        facts nobody typed, which is what makes them worth comparing —
        "Quadratics took 4 lessons and 3h 20m" is checkable in a way that
        "Quadratics was 70%" never was.
        """
        entries = self.lessons.filter(voided=False).select_related("lesson")
        if syllabus is not None:
            entries = entries.filter(lesson__syllabus=syllabus)
        lessons = [e.lesson for e in entries if not e.lesson.voided]
        seconds = sum(lesson.teaching_seconds for lesson in lessons)
        return {
            "lessons": len(lessons),
            "seconds": seconds,
            "display": f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m" if seconds else "",
            "finished": any(e.covered for e in entries),
        }

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
    pass_mark_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("50.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "The mark a topic result must reach to count as passed. Stored "
            "here rather than on the result, so raising or lowering the bar "
            "re-reads the whole year's history without re-entering a mark."
        ),
    )

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

    def assessable_sections(self):
        """
        [(section topic, [leaf topics])] in teaching order.

        A syllabus lists its sections; the teaching happens in the things
        under them. Assessing the leaf and rolling the section up from its
        children keeps one topic from being counted twice, and makes the
        percentage mean something — "31 of 68 topics" rather than "1 of 12
        sections". A section with no children is its own leaf, so a flat
        subject still works.
        """
        listed = list(
            self.topics.filter(voided=False)
            .select_related("topic")
            .order_by("sort_order")
        )
        if not listed:
            return []

        children = {}
        for topic in Topic.objects.filter(
            subject_id=self.subject_id, voided=False
        ).order_by("sort_order", "short_name"):
            children.setdefault(topic.parent_id, []).append(topic)

        def leaves_of(topic):
            kids = children.get(topic.pk, [])
            if not kids:
                return [topic]
            found = []
            for kid in kids:
                found.extend(leaves_of(kid))
            return found

        return [(row.topic, leaves_of(row.topic)) for row in listed]

    def assessable_topics(self):
        """Every leaf a student is marked against, flattened."""
        return [
            leaf for _section, leaves in self.assessable_sections() for leaf in leaves
        ]


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

    # -- progress ------------------------------------------------------
    def progress(self):
        """
        How far through the subject this student is.

        Percent completion is passed topics over the topics the syllabus
        makes assessable — the plain reading of "12 of 20 topics passed is
        60%". A topic assessed and failed counts as attempted, not as
        progress, so the number only ever goes up by passing something.
        """
        topics = self.syllabus.assessable_topics()
        pass_mark = self.syllabus.pass_mark_pct
        results = {
            result.topic_id: result
            for result in self.topic_results.filter(voided=False)
        }

        passed = assessed = 0
        for topic in topics:
            result = results.get(topic.pk)
            if result is None or result.score_pct is None:
                continue
            assessed += 1
            if result.score_pct >= pass_mark:
                passed += 1

        total = len(topics)
        return {
            "total": total,
            "assessed": assessed,
            "passed": passed,
            "percent": round(passed * 100 / total) if total else 0,
            "pass_mark": pass_mark,
        }


class TopicResult(AuditModel):
    """
    Where one student stands on one topic of one subject in one year.

    This is the row the knowledge map reads. It hangs off StudentSubject
    rather than off the student, so a topic taken again in a later grade
    is a separate result and the earlier one stays as it was recorded.

    `score_pct` is the mark out of a hundred. Whether that is a pass is
    not stored: it is the syllabus's `pass_mark_pct` that decides, read at
    the moment the question is asked.
    """

    student_subject = models.ForeignKey(
        StudentSubject, on_delete=models.PROTECT, related_name="topic_results"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.PROTECT, related_name="student_results"
    )
    score_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Out of 100. Empty means the topic has not been assessed yet.",
    )
    assessed_on = models.DateField(null=True, blank=True)
    method = models.CharField(
        max_length=16, choices=EvalMethod.choices, default=EvalMethod.TEACHER,
        help_text="Who or what produced the mark: a teacher, a rule, or the AI marker.",
    )
    note = models.TextField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "topic_result"
        ordering = ["topic__sort_order", "topic__short_name"]
        indexes = [models.Index(fields=["topic", "student_subject"])]
        constraints = [
            unique_active(["student_subject", "topic"], "topic_result_uix"),
        ]

    def __str__(self):
        score = "—" if self.score_pct is None else f"{self.score_pct:g}%"
        return f"{self.student_subject} · {self.topic.short_name} · {score}"

    def clean(self):
        """A result may only be recorded against a topic of that subject."""
        if self.topic_id and self.student_subject_id:
            if self.topic.subject_id != self.student_subject.syllabus.subject_id:
                raise ValidationError({
                    "topic": "That topic belongs to a different subject.",
                })

    @property
    def passed(self):
        """None while unassessed — not the same as failed."""
        if self.score_pct is None:
            return None
        return self.score_pct >= self.student_subject.syllabus.pass_mark_pct

    @property
    def status(self):
        """
        The mark the knowledge map draws for this topic.

        Two states only, because the third — never taken — is a fact about
        the subject, not about a result that exists. A topic assessed
        below the pass mark is still "studying": the student is on it and
        has not passed it yet, which is what a reader of the map needs to
        know. The score itself is on the row for anyone who wants more.
        """
        if self.passed:
            return SubjectStatus.PASSED
        return SubjectStatus.STUDYING


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
# ---------------------------------------------------------------------
# Timetable and lessons
# ---------------------------------------------------------------------
class TimetableSlot(AuditModel):
    """
    The weekly pattern: one subject, one grade, one day, one period.

    Set once and changed rarely. It is a template, not a record of what
    happened — the lesson actually taught is a `Lesson`, created from this
    slot. Keeping them apart is what lets a teacher swap a day without
    rewriting the weeks already taught.

    Breaks are not modelled. Nothing is logged against them, so the grid
    holds only the periods that are lessons.
    """

    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.PROTECT, related_name="timetable_slots",
        help_text="The subject, grade and year this slot teaches.",
    )
    teacher = models.ForeignKey(
        Teacher, on_delete=models.PROTECT, null=True, blank=True,
        related_name="timetable_slots",
        help_text="Who normally teaches it. A lesson may name someone else.",
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DayOfWeek.choices)
    period = models.CharField(
        max_length=32,
        help_text="Period label, matching the one used on registers — '1', '2', 'assembly'.",
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta(AuditModel.Meta):
        db_table = "timetable_slot"
        ordering = ["day_of_week", "period"]
        indexes = [models.Index(fields=["day_of_week", "period"])]
        constraints = [
            unique_active(
                ["syllabus", "day_of_week", "period"], "timetable_slot_uix"
            ),
        ]

    def __str__(self):
        return f"{self.syllabus} · {self.get_day_of_week_display()} {self.period}"


class Lesson(AuditModel):
    """
    One class, on one date — the thing a teacher actually stands up and
    teaches, and the row everything about that class hangs off.

    Created from a `TimetableSlot`, but editable on its own, so a swapped
    day changes that lesson and leaves the pattern and the weeks already
    taught alone.

    Course content is built up as the year runs, so a lesson is drafted by
    its teacher, submitted, and approved by a Head of Department before it
    counts as course content. `status` carries that; nothing reaches
    students until it is APPROVED.

    Lecture material attaches through `attachments`, the same generic link
    every other file in the system uses.
    """

    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.PROTECT, related_name="lessons"
    )
    slot = models.ForeignKey(
        TimetableSlot, on_delete=models.PROTECT, null=True, blank=True,
        related_name="lessons",
        help_text="The weekly slot this came from. Empty for a one-off lesson.",
    )
    teacher = models.ForeignKey(
        Teacher, on_delete=models.PROTECT, null=True, blank=True,
        related_name="lessons", help_text="Who taught it, if not the usual teacher.",
    )
    date = models.DateField()
    period = models.CharField(max_length=32)
    title = models.CharField(max_length=256, blank=True, default="")

    plan = models.TextField(
        blank=True, default="",
        help_text="What will be taught, prepared in advance and reviewed by the head.",
    )
    plan_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    log = models.TextField(
        blank=True, default="",
        help_text="Written after the lesson: what was actually covered, and anything "
                  "the class needs.",
    )
    log_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )
    date_taught = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when the teacher logs the lesson. Empty means it was never "
                  "written up — which is what the compliance view looks for.",
    )

    # How long the class actually took. The teacher starts a timer when
    # they begin, pauses it if they break off, and stops at the end.
    # Two fields carry it: the seconds banked so far, and when the current
    # run began. Running means `timer_started_at` is set.
    #
    # The point is not surveillance. A topic that repeatedly overruns is
    # the single most useful thing to know when planning next year, and
    # nobody can reconstruct it from memory in June.
    teaching_seconds = models.PositiveIntegerField(
        default=0, help_text="Time actually spent teaching, in seconds.",
    )
    timer_started_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set while the timer runs; cleared when paused or stopped.",
    )
    timer_status = models.CharField(
        max_length=8, choices=TimerStatus.choices, default=TimerStatus.IDLE,
        help_text="Recorded rather than guessed. Inferring it from the other "
                  "fields made a pause after an ended class read as ended, so "
                  "the teacher was offered Start instead of Resume.",
    )

    status = models.CharField(
        max_length=16, choices=LessonStatus.choices, default=LessonStatus.DRAFT
    )
    date_submitted = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="lessons_submitted",
    )
    date_reviewed = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="lessons_reviewed",
    )
    review_comment = models.TextField(
        blank=True, default="",
        help_text="Why it was returned. The point of review is improving the "
                  "lesson, not only gating it.",
    )

    attachments = GenericRelation("AttachmentLink", related_query_name="lesson")

    class Meta(AuditModel.Meta):
        db_table = "lesson"
        ordering = ["-date", "period"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["teacher", "date"]),
        ]
        constraints = [
            unique_active(["syllabus", "date", "period"], "lesson_uix"),
        ]

    def __str__(self):
        return f"{self.syllabus} · {self.date} {self.period}"

    @property
    def is_approved(self):
        return self.status == LessonStatus.APPROVED

    @property
    def is_logged(self):
        """Whether the teacher wrote the lesson up after teaching it."""
        return bool(self.date_taught)

    # -- the class timer ----------------------------------------------
    @property
    def timer_running(self):
        return self.timer_status == TimerStatus.RUNNING and self.timer_started_at

    @property
    def elapsed_seconds(self):
        """Banked seconds, plus the run in progress if there is one."""
        total = self.teaching_seconds
        if self.timer_started_at:
            total += int((timezone.now() - self.timer_started_at).total_seconds())
        return total

    @property
    def elapsed_display(self):
        seconds = self.elapsed_seconds
        return f"{seconds // 3600:d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

    def timer_start(self):
        """Start, resume, or pick the class up again after it ended."""
        if not self.timer_started_at:
            self.timer_started_at = timezone.now()
        self.timer_status = TimerStatus.RUNNING
        self.save(update_fields=["timer_started_at", "timer_status", "date_changed"])
        return self

    def timer_pause(self, status=None):
        """Bank the run in progress. Starting again adds to it."""
        if self.timer_started_at:
            self.teaching_seconds = self.elapsed_seconds
            self.timer_started_at = None
        self.timer_status = status or TimerStatus.PAUSED
        self.save(update_fields=["teaching_seconds", "timer_started_at",
                                 "timer_status", "date_changed"])
        return self

    def timer_stop(self):
        """End of the class: bank the time and mark the lesson taught."""
        self.timer_pause(status=TimerStatus.ENDED)
        if not self.date_taught:
            self.date_taught = timezone.now()
            self.save(update_fields=["date_taught", "date_changed"])
        return self

    @property
    def topic_counts(self):
        """{done, total} across the topics this lesson planned to cover."""
        planned = [t for t in self.topics.all() if t.planned and not t.voided]
        return {"done": len([t for t in planned if t.covered]), "total": len(planned)}

    def unfinished_topics(self):
        return [
            t.topic for t in self.topics.all()
            if t.planned and not t.voided and not t.covered
        ]

    def next_lesson(self):
        """The next class for this syllabus, which is where leftovers go."""
        return (
            Lesson.objects
            .filter(syllabus=self.syllabus, voided=False, date__gt=self.date)
            .order_by("date", "period")
            .first()
        )

    def carry_forward(self):
        """
        Put anything unfinished onto the next lesson.

        This is the whole reason a teacher bothers to log: the system
        remembers where they stopped and puts it in front of them next
        time, rather than asking them to remember.
        """
        following = self.next_lesson()
        if following is None:
            return []
        moved = []
        for topic in self.unfinished_topics():
            entry, created = LessonTopic.objects.get_or_create(
                lesson=following, topic=topic, voided=False,
                defaults={"planned": True, "carried": True},
            )
            if created:
                moved.append(topic)
        return moved

    def submit(self, user=None):
        """Teacher hands the lesson to the head for review."""
        self.status = LessonStatus.SUBMITTED
        self.date_submitted = timezone.now()
        self.submitted_by = user
        self.save()
        return self

    def approve(self, user=None):
        """Head signs it off. From here it is course content."""
        self.status = LessonStatus.APPROVED
        self.date_reviewed = timezone.now()
        self.reviewed_by = user
        self.review_comment = ""
        self.save()
        return self

    def return_for_changes(self, user=None, comment=""):
        """Send it back to the teacher, with a reason."""
        self.status = LessonStatus.RETURNED
        self.date_reviewed = timezone.now()
        self.reviewed_by = user
        self.review_comment = comment
        self.save()
        return self


class LessonTopic(AuditModel):
    """
    A topic a lesson plans to cover, and whether it actually was.

    `covered` is a plain yes or no, deliberately. A percentage would be a
    number the teacher invents under time pressure at the end of a class,
    and one teacher's 70% is not another's — it reads like data without
    being comparable. Done or not finished is answerable in two seconds
    and means the same thing to everyone.

    Nothing is lost by that, because the questions worth asking are
    answered by counting rather than by estimating: how many lessons a
    topic took, and how many minutes, both come from facts the system
    already holds. `Topic.teaching_summary` does that arithmetic.

    An unfinished topic is carried onto the next lesson automatically, so
    logging helps the teacher rather than only reporting on them.
    """

    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="topics")
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="lessons")
    planned = models.BooleanField(default=True)
    covered = models.BooleanField(
        default=False, help_text="Ticked when the lesson is logged after teaching."
    )
    note = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Why it was left short, if it was. Never analysed — it is "
                  "for the person reading it next week.",
    )
    carried = models.BooleanField(
        default=False,
        help_text="Put here automatically because the last lesson did not "
                  "finish it. The teacher did not have to carry it forward.",
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")

    #: Lecture notes for this topic. A topic with its own material shows
    #: it here; otherwise the lesson's own materials stand for the class.
    attachments = GenericRelation("AttachmentLink", related_query_name="lesson_topic")

    class Meta(AuditModel.Meta):
        db_table = "lesson_topic"
        ordering = ["lesson", "sort_order"]
        constraints = [
            unique_active(["lesson", "topic"], "lesson_topic_uix"),
        ]

    def __str__(self):
        return f"{self.lesson} · {self.topic}"

    def materials(self):
        return [
            link.attachment for link in self.attachments.all()
            if not link.voided and link.attachment_id
        ]


# ---------------------------------------------------------------------
# Handouts and what students hand back
# ---------------------------------------------------------------------
class LectureItem(AuditModel):
    """
    One row of a lesson's lecture table: where in the book, and the file.

    Deliberately plain text rather than links to `Topic`. A teacher adding
    material at 7.40am should be able to type "Unit 3, Chapter 2" without
    anything having been catalogued first, and different subjects number
    their books differently. `LessonTopic` still carries the catalogued
    topics for logging and carrying forward — these two answer different
    questions and are kept apart on purpose.

    Every field is optional, including the file. A row with only a chapter
    written on it is a legitimate note to self.

    There is no sub-topic column: the log's "parts done" checklist already
    answers that question, and asking twice is how a form starts feeling
    like paperwork.
    """

    lesson = models.ForeignKey(
        Lesson, on_delete=models.PROTECT, related_name="lecture_items"
    )
    unit = models.CharField(max_length=128, blank=True, default="")
    chapter = models.CharField(max_length=128, blank=True, default="")
    topic = models.CharField(max_length=255, blank=True, default="")
    attachment = models.ForeignKey(
        "Attachment", on_delete=models.PROTECT, null=True, blank=True,
        related_name="lecture_items",
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")

    class Meta(AuditModel.Meta):
        db_table = "lecture_item"
        ordering = ["lesson", "sort_order", "id"]

    def __str__(self):
        parts = [p for p in (self.unit, self.chapter, self.topic) if p]
        return " · ".join(parts) or (str(self.attachment) if self.attachment else "—")

    @property
    def is_empty(self):
        return not any((self.unit, self.chapter, self.topic, self.attachment_id))


class Handout(AuditModel):
    """
    A sheet given out in class, and the work handed back from it.

    Deliberately lighter than the exam machinery. A teacher writing
    tonight's homework should attach a sheet and hand it out, not build a
    versioned question paper — that route exists, and is right for a
    formal exam, and wrong for a Tuesday.

    Printed copies are identical, so nothing on the page identifies the
    student. `code` identifies the *handout*, and a submission carries its
    own code stamped with the moment it arrived. Together they say which
    sheet, whose work, and which attempt.

    A handout hangs off a syllabus rather than a single lesson, and its
    lessons are listed in `HandoutLesson`, so one sheet may cover a week
    of classes or a lesson may carry several sheets.
    """

    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.PROTECT, related_name="handouts"
    )
    code = models.CharField(
        max_length=64, editable=False,
        help_text="Set on first save: subject, grade, year and a running "
                  "number, e.g. ENG-E1-2026-H007. Printed on the sheet and "
                  "quoted by every submission.",
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.PROTECT, null=True, blank=True,
        related_name="handouts",
        help_text="The topic it belongs to, so it shows beside that topic on "
                  "the teacher's day. Optional.",
    )
    title = models.CharField(max_length=256)
    # Where in the book it comes from, typed rather than catalogued — the
    # same reasoning as LectureItem. `topic` above is the catalogued link
    # and stays optional; these two are what a teacher actually writes.
    chapter = models.CharField(max_length=128, blank=True, default="")
    topic_text = models.CharField(
        max_length=255, blank=True, default="", verbose_name="topic (as written)",
    )
    instructions = models.TextField(blank=True, default="")
    instructions_format = models.CharField(
        max_length=16, choices=TextFormat.choices, default=TextFormat.MARKDOWN
    )

    is_assignment = models.BooleanField(
        default=True,
        help_text="Students hand work back from it. Clear it for a sheet that "
                  "is only to read.",
    )
    kind = models.CharField(
        max_length=16, choices=HandoutKind.choices, default=HandoutKind.ASSIGNMENT,
        help_text="An assignment is set in class; the exam kinds are sat under "
                  "supervision and are never shown to a class in advance.",
    )
    # Weight is inherited from the topic, not typed per paper. A teacher
    # who rates a topic once when planning the year never has to weigh a
    # test again. The override is for the occasional paper that does not
    # deserve its topic's weight; empty means inherit, which is the
    # normal case.
    weight_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="weight override",
        help_text="Leave empty to inherit the topic's importance. Set it only "
                  "for a paper that should count more or less than its topic.",
    )
    counts_toward_grade = models.BooleanField(
        default=True,
        help_text="Clear it for practice work that is marked but should not "
                  "move the student's average.",
    )
    # Three dates, because they answer three different questions. The
    # due date is when work is expected; the cut-off is when the door
    # actually shuts. Between them, work is accepted and marked late —
    # which is a fact worth keeping rather than a door slammed. Leave the
    # cut-off empty to accept late work indefinitely; set it equal to the
    # due date for a hard stop. (Moodle's model, and it has held up.)
    open_from = models.DateTimeField(
        null=True, blank=True,
        help_text="Students see it from this moment. Empty means as soon as "
                  "it is posted.",
    )
    due_date = models.DateField(
        null=True, blank=True, help_text="When the work is expected.",
    )
    allow_late = models.BooleanField(
        default=False,
        help_text="Keep taking work after the due date, marked late. Off "
                  "means the due date is the close.",
    )
    cutoff_at = models.DateTimeField(
        null=True, blank=True, verbose_name="late submissions until",
        help_text="Only used when late submissions are allowed. Empty then "
                  "means late work is taken indefinitely.",
    )
    max_marks = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    max_rounds = models.PositiveSmallIntegerField(
        default=3,
        help_text="Submissions allowed, counting the first. Three means one "
                  "attempt and two redoes; after that it goes to the teacher.",
    )

    status = models.CharField(
        max_length=16, choices=HandoutStatus.choices, default=HandoutStatus.DRAFT
    )
    date_activated = models.DateTimeField(
        null=True, blank=True,
        help_text="When it was handed out. Until then students cannot see it.",
    )
    activated_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="handouts_activated",
    )

    #: The sheet itself, and the answer scheme, both attach here. The link's
    #: `role` separates them: "handout" is given out, "scheme" never is.
    attachments = GenericRelation("AttachmentLink", related_query_name="handout")

    class Meta(AuditModel.Meta):
        db_table = "handout"
        ordering = ["-date_created"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["due_date"])]
        constraints = [unique_active(["code"], "handout_code_uix")]

    def __str__(self):
        return f"{self.code} · {self.title}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._next_code()
        return super().save(*args, **kwargs)

    def _next_code(self):
        """`<SUBJECT>-<GRADE>-<YEAR>-H<nnn>`, counting within the syllabus."""
        syllabus = self.syllabus
        prefix = "{}-{}-{}-H".format(
            syllabus.subject.short_name,
            syllabus.grade.short_name,
            syllabus.academic_year,
        )
        taken = (
            Handout.all_objects
            .filter(syllabus=syllabus, code__startswith=prefix)
            .values_list("code", flat=True)
        )
        highest = 0
        for code in taken:
            tail = code[len(prefix):]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"{prefix}{highest + 1:03d}"

    # -- handing it out -------------------------------------------------
    def activate(self, user=None):
        """Hand it out. From here the class can see it and submit against it."""
        self.status = HandoutStatus.ACTIVE
        self.date_activated = timezone.now()
        self.activated_by = user
        self.save()
        return self

    def close(self, user=None):
        self.status = HandoutStatus.CLOSED
        self.save()
        return self

    @property
    def is_open(self):
        return self.status == HandoutStatus.ACTIVE

    @property
    def has_submissions(self):
        return Submission.objects.filter(handout=self, voided=False).exists()

    @property
    def can_unpost(self):
        """
        Only while nobody has handed anything in.

        Unposting after that hides work a student has already done, and a
        student who cannot see their own submission assumes it was lost.
        Canvas refuses outright for the same reason; so do we.
        """
        return not self.has_submissions

    # -- weight ---------------------------------------------------------
    @property
    def is_exam(self):
        """Sat under supervision, so it is never shown to a class in advance."""
        return self.kind in {
            HandoutKind.ASSESSMENT, HandoutKind.MOCK, HandoutKind.QUARTERLY,
        }

    @property
    def topic_importance(self):
        """
        The importance of the topic this paper is set on.

        Topics nest, and only syllabus sections carry a weight, so a paper
        set on a leaf topic reads the weight of the nearest ancestor that
        has one. Returns None when the paper is not tied to a catalogued
        topic at all.
        """
        if not self.topic_id:
            return None
        # The topic itself, then its ancestors, nearest first.
        candidates = [self.topic_id]
        path = (self.topic.path or "").strip("/")
        if path:
            candidates += [int(x) for x in reversed(path.split("/")) if x.isdigit()]
        rows = {
            st.topic_id: st.weight_pct
            for st in SyllabusTopic.objects.filter(
                syllabus_id=self.syllabus_id, topic_id__in=candidates, voided=False,
            )
        }
        for topic_id in candidates:
            if rows.get(topic_id) is not None:
                return rows[topic_id]
        return None

    @property
    def effective_weight(self):
        """
        What this paper actually counts for, resolved rather than typed.

        The override wins if one was set; otherwise the topic's importance;
        otherwise Standard. A paper marked as not counting returns zero, so
        it can stay in the list and out of the average.
        """
        if not self.counts_toward_grade:
            return Decimal("0")
        if self.weight_override is not None:
            return Decimal(self.weight_override)
        inherited = self.topic_importance
        if inherited is not None:
            return Decimal(inherited)
        return Decimal(TopicImportance.STANDARD.value)

    @property
    def weight_label(self):
        """The resolved weight said in words, for a chip on the teacher's page."""
        if not self.counts_toward_grade:
            return "Practice only"
        weight = self.effective_weight
        best = min(
            TopicImportance.choices, key=lambda c: abs(Decimal(c[0]) - weight)
        )
        suffix = "" if self.weight_override is None else " (set on this paper)"
        return f"{best[1]}{suffix}"

    @property
    def due_moment(self):
        """The due date as a moment: the end of that day."""
        if not self.due_date:
            return None
        return timezone.make_aware(
            datetime.combine(self.due_date, datetime_time(23, 59, 59)),
            timezone.get_current_timezone(),
        )

    def deadline_for(self, enrolment=None):
        """
        When this student's door shuts, and when their work counts as late.

        An extension moves both for that student only. Everything else —
        the sheet, the code, the marks — stays shared, which is what keeps
        one column in the gradebook instead of two.
        """
        due = self.due_moment
        # Without late submissions the due date is the close. With them,
        # the close is whenever the teacher said — or never, if they left
        # it empty.
        cutoff = self.cutoff_at if self.allow_late else due
        if enrolment is not None:
            extension = HandoutExtension.objects.filter(
                handout=self, enrolment=enrolment, voided=False
            ).order_by("-extended_to").first()
            if extension:
                due = extension.extended_to
                if cutoff is None or extension.extended_to > cutoff:
                    cutoff = extension.extended_to
        return {"due": due, "cutoff": cutoff}

    def accepts_submission(self, enrolment=None, at=None):
        """Whether work may be handed in now, and why not if it may not."""
        at = at or timezone.now()
        if self.status != HandoutStatus.ACTIVE:
            return False, "This handout has not been posted."
        if self.open_from and at < self.open_from:
            return False, "This handout is not open yet."
        dates = self.deadline_for(enrolment)
        if dates["cutoff"] and at > dates["cutoff"]:
            return False, "The closing time for this handout has passed."
        return True, ""

    @property
    def is_past_due(self):
        due = self.due_moment
        return bool(due and timezone.now() > due)

    @property
    def late_window_open(self):
        """Past the due date, but still taking work."""
        if not (self.allow_late and self.is_past_due):
            return False
        return not self.cutoff_at or timezone.now() <= self.cutoff_at

    def lateness(self, enrolment=None, at=None):
        """Minutes past the due moment, or 0 if it is on time."""
        at = at or timezone.now()
        due = self.deadline_for(enrolment)["due"]
        if not due or at <= due:
            return 0
        return int((at - due).total_seconds() // 60)

    @property
    def current_sheet(self):
        return self.sheets.filter(voided=False, replaced_on__isnull=True).first()

    @property
    def sheet_version_no(self):
        sheet = self.current_sheet
        return sheet.version_no if sheet else 0

    def add_sheet(self, attachment, note=""):
        """
        Make this file the sheet, as the next version.

        The one it replaces is kept and stamped, so a submission that
        answered version 1 still points at the paper it was actually given.
        """
        current = self.current_sheet
        if current and current.attachment_id == attachment.pk:
            return current
        if current:
            current.replaced_on = timezone.now()
            current.save(update_fields=["replaced_on", "date_changed"])
        last = (
            HandoutSheet.all_objects.filter(handout=self)
            .order_by("-version_no").first()
        )
        return HandoutSheet.objects.create(
            handout=self, attachment=attachment,
            version_no=(last.version_no + 1) if last else 1,
            note=note,
        )

    def files(self, role="handout"):
        """Attachments with one role — the sheet, or the answer scheme."""
        return [
            link.attachment for link in self.attachments.all()
            if not link.voided and link.role == role and link.attachment_id
        ]

    def enrolments(self):
        """Everyone the handout is for: the grade's live enrolments this year."""
        return Enrolment.objects.filter(
            grade=self.syllabus.grade,
            academic_year=self.syllabus.academic_year,
            voided=False,
        ).select_related("student")

    def to_check(self):
        """Work handed in and not yet checked."""
        return Submission.objects.filter(
            handout=self, voided=False, state=SubmissionState.SUBMITTED
        )

    def completion(self):
        """{submitted, outstanding, total} — the class's progress on it."""
        enrolments = list(self.enrolments())
        submitted = set(
            Submission.objects
            .filter(handout=self, voided=False)
            .values_list("enrolment_id", flat=True)
        )
        return {
            "total": len(enrolments),
            "submitted": len([e for e in enrolments if e.id in submitted]),
            "outstanding": len([e for e in enrolments if e.id not in submitted]),
        }


class HandoutLesson(AuditModel):
    """
    Which lessons a handout belongs to.

    Usually one. A sheet covering a week of classes lists several, and a
    lesson carrying both classwork and homework appears in two handouts.
    """

    handout = models.ForeignKey(Handout, on_delete=models.PROTECT, related_name="lessons")
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="handouts")
    sort_order = models.IntegerField(default=0, verbose_name="sort")

    class Meta(AuditModel.Meta):
        db_table = "handout_lesson"
        ordering = ["handout", "sort_order"]
        constraints = [unique_active(["handout", "lesson"], "handout_lesson_uix")]

    def __str__(self):
        return f"{self.handout.code} · {self.lesson}"


class HandoutSheet(AuditModel):
    """
    One version of the sheet students were given.

    A teacher will find a typo at eight in the evening, after half the
    class has handed in. Blocking the edit means deleting and re-posting,
    which strands everyone who already submitted; editing in place means
    a mark refers to a sheet that no longer exists. So a replacement
    becomes version 2, the earlier one stays exactly as it was issued, and
    every submission records which version it answered.

    The same reasoning as `PaperVersion`, at a lighter weight: no locking
    workflow, because a handout is posted rather than approved.
    """

    handout = models.ForeignKey(
        Handout, on_delete=models.PROTECT, related_name="sheets"
    )
    version_no = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    attachment = models.ForeignKey(
        "Attachment", on_delete=models.PROTECT, related_name="handout_sheets"
    )
    note = models.CharField(
        max_length=255, blank=True, default="",
        help_text="What changed, for whoever reads this later.",
    )
    replaced_on = models.DateTimeField(
        null=True, blank=True,
        help_text="When a later version took over. Empty on the current one.",
    )

    class Meta(AuditModel.Meta):
        db_table = "handout_sheet"
        ordering = ["handout", "-version_no"]
        constraints = [
            unique_active(["handout", "version_no"], "handout_sheet_uix"),
        ]

    def __str__(self):
        return f"{self.handout.code} v{self.version_no}"

    @property
    def is_current(self):
        return self.replaced_on is None


class HandoutExtension(AuditModel):
    """
    A later deadline for one student on one handout.

    Not a second handout: the same sheet, the same code, the same marks
    column — only the date moves, and only for this student. Issuing a
    fresh handout instead would double-count the work and split the
    record in two, which is why every established system does it this way.
    """

    handout = models.ForeignKey(
        Handout, on_delete=models.PROTECT, related_name="extensions"
    )
    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.PROTECT, related_name="handout_extensions"
    )
    extended_to = models.DateTimeField(help_text="Their new deadline.")
    reason = models.CharField(max_length=255, blank=True, default="")
    granted_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="extensions_granted",
    )

    class Meta(AuditModel.Meta):
        db_table = "handout_extension"
        ordering = ["handout", "enrolment"]
        constraints = [
            unique_active(["handout", "enrolment"], "handout_extension_uix"),
        ]

    def __str__(self):
        return f"{self.handout.code} · {self.enrolment.student} · {self.extended_to:%d %b %H:%M}"


class Submission(AuditModel):
    """
    One student's work handed back for one handout, in one round.

    `code` is stamped with the moment it arrived, so it identifies this
    hand-in and no other: `<handout code>-<admission no>-<timestamp>`.
    Printed copies are identical, so this is what tells the two apart.

    A round is one pass through marking. Round 1 is the first hand-in;
    a redo of the questions marked wrong is round 2, and so on up to the
    handout's `max_rounds`. Nothing is overwritten — each round is its own
    row, and the marks are read across all of them.
    """

    handout = models.ForeignKey(Handout, on_delete=models.PROTECT, related_name="submissions")
    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.PROTECT, related_name="submissions",
        help_text="Whose work, and in which grade and year — so the record "
                  "stays true after they move up.",
    )
    code = models.CharField(
        max_length=128, editable=False,
        help_text="Stamped with the moment it arrived. Identifies this "
                  "hand-in and no other.",
    )
    round_no = models.PositiveSmallIntegerField(
        default=1,
        help_text="1 is the first hand-in; 2 and 3 are redoes of the "
                  "questions marked wrong. 'Right first time' is worth "
                  "keeping, so this is never overwritten.",
    )
    time_submitted = models.DateTimeField(default=timezone.now)
    state = models.CharField(
        max_length=16, choices=SubmissionState.choices,
        default=SubmissionState.SUBMITTED,
    )
    awarded_marks = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="This round's marks. The running total across rounds is "
                  "worked out, not stored.",
    )
    sheet_version = models.PositiveIntegerField(
        default=0,
        help_text="Which version of the sheet this answered. 0 for work "
                  "handed in before sheets were versioned.",
    )
    is_late = models.BooleanField(
        default=False,
        help_text="Handed in after the due moment. Late is recorded, not "
                  "refused — the cut-off is what refuses.",
    )
    minutes_late = models.PositiveIntegerField(default=0)
    feedback = models.TextField(blank=True, default="")
    marked_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="submissions_marked",
        help_text="The examiner who checked it.",
    )
    date_marked = models.DateTimeField(null=True, blank=True)

    # The teacher's sign-off. A mark the examiner produced is not released
    # to the student until the class teacher approves it here.
    approved_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="submissions_approved",
        help_text="The teacher who released this to the student.",
    )
    date_approved = models.DateTimeField(null=True, blank=True)
    sent_back_reason = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Why the teacher returned this to the examiner to re-check.",
    )

    # A redo happens only when a teacher asks for one on this particular
    # piece of work. Nothing comes back automatically: most work is
    # checked, returned and finished with.
    redo_requested_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="redos_requested",
    )
    date_redo_requested = models.DateTimeField(null=True, blank=True)
    redo_reason = models.CharField(
        max_length=255, blank=True, default="",
        help_text="What the student is being asked to put right.",
    )

    attachments = GenericRelation("AttachmentLink", related_query_name="submission")

    class Meta(AuditModel.Meta):
        db_table = "submission"
        ordering = ["-time_submitted"]
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["handout", "enrolment"]),
        ]
        constraints = [
            unique_active(
                ["handout", "enrolment", "round_no"], "submission_round_uix"
            ),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            stamp = timezone.localtime(self.time_submitted or timezone.now())
            self.code = "{}-{}-{}".format(
                self.handout.code,
                self.enrolment.student.admission_no,
                stamp.strftime("%Y%m%d%H%M%S"),
            )
        return super().save(*args, **kwargs)

    @property
    def student(self):
        return self.enrolment.student

    @property
    def is_final_round(self):
        return self.round_no >= self.handout.max_rounds

    @property
    def is_checked(self):
        """The examiner has produced a checked result (approved or not)."""
        return self.state in (
            SubmissionState.MARKED, SubmissionState.APPROVED,
            SubmissionState.ACCEPTED, SubmissionState.RETURNED,
        )

    @property
    def awaits_approval(self):
        """Checked by the examiner, sitting in the teacher's approval list."""
        return self.state == SubmissionState.MARKED

    @property
    def is_released(self):
        """Approved by the teacher — the student may see the mark and file."""
        return self.state in (SubmissionState.APPROVED, SubmissionState.RETURNED)

    @property
    def sent_back(self):
        """The teacher returned it to the examiner to re-check."""
        return self.state == SubmissionState.SENT_BACK

    @property
    def marks_total(self):
        """Marks available, from the breakdown if there is one."""
        lines = [l for l in self.mark_lines.all() if not l.voided]
        if lines:
            return sum((l.out_of or Decimal("0")) for l in lines)
        return self.handout.max_marks

    @property
    def marks_awarded(self):
        """Marks given, from the breakdown if there is one."""
        lines = [l for l in self.mark_lines.all() if not l.voided]
        if lines:
            return sum((l.awarded or Decimal("0")) for l in lines)
        return self.awarded_marks

    @property
    def percentage(self):
        """
        This piece of work as a percentage.

        The percentage is what aggregates, never the raw marks: a sheet
        out of 50 and a sheet out of 10 say the same thing about a student
        once both are on a scale of a hundred, and letting raw marks
        aggregate would make the longer sheet count for five times more by
        accident rather than by anyone's decision.
        """
        total = self.marks_total
        awarded = self.marks_awarded
        if not total or awarded is None:
            return None
        return (Decimal(awarded) / Decimal(total) * 100).quantize(Decimal("0.01"))

    @property
    def has_auto_marks(self):
        return any(
            l.source == MarkSource.AUTO for l in self.mark_lines.all() if not l.voided
        )

    @property
    def needs_examiner(self):
        """
        On the examiner's plate: waiting, open in front of them, or bounced back.

        GRADING belongs here. It means an examiner has opened the script —
        which locks the student out of replacing it — and a piece of work
        someone opened and walked away from must stay in the queue, or it
        is quietly lost.
        """
        return self.state in (
            SubmissionState.SUBMITTED,
            SubmissionState.GRADING,
            SubmissionState.SENT_BACK,
        )

    def replaceable(self, at=None):
        """
        Whether the student may still overwrite this hand-in.

        Two gates, and whichever closes first wins: the submission window,
        and the examiner opening the script. The wrong file uploaded at
        eleven at night is a mistake worth forgiving; a file that changes
        underneath the person marking it is not.
        """
        if self.voided or self.state != SubmissionState.SUBMITTED:
            return False
        allowed, _why = self.handout.accepts_submission(self.enrolment, at=at)
        return allowed

    def start_checking(self, user=None):
        """
        The examiner has opened it, so the file may no longer change.

        Only a first, never-checked hand-in moves. Anything already marked,
        approved or sent back is well past this point and is left alone.
        """
        if self.state == SubmissionState.SUBMITTED:
            self.state = SubmissionState.GRADING
            self.save(update_fields=["state"])
        return self

    @property
    def awaits_redo(self):
        """The teacher asked the student to do this one again."""
        return self.state == SubmissionState.RETURNED

    def work_files(self):
        """What the student handed in."""
        return [
            link.attachment for link in self.attachments.all()
            if not link.voided and link.role == "work" and link.attachment_id
        ]

    def checked_files(self):
        """
        What the examiner handed back.

        The same file the student sees, the teacher sees and — later — a
        guardian sees. One upload, several audiences, no copies.
        """
        return [
            link.attachment for link in self.attachments.all()
            if not link.voided and link.role == "checked" and link.attachment_id
        ]

    def lines(self):
        """The marks breakdown, in the order the examiner entered it."""
        return list(self.mark_lines.filter(voided=False))

    def line_totals(self):
        """
        What the breakdown adds up to.

        Returned even when there are no lines, so a caller never has to
        check first: awarded and out_of are then both zero.
        """
        lines = self.lines()
        return {
            "awarded": sum((line.awarded or 0) for line in lines),
            "out_of": sum((line.out_of or 0) for line in lines),
            "count": len(lines),
        }

    def mark(self, user=None, marks=None, feedback=""):
        """
        Record the result.

        `awarded_marks` stays the single number everything else reads, but
        once a breakdown exists it is the sum of the lines rather than a
        figure typed separately — two totals that can disagree is one
        total too many.
        """
        totals = self.line_totals()
        self.awarded_marks = totals["awarded"] if totals["count"] else marks
        self.feedback = feedback
        self.marked_by = user
        self.date_marked = timezone.now()
        # Checked, but held for the teacher: MARKED means "waiting for
        # approval", not "released". A re-check after a send-back clears the
        # send-back note and puts it back in front of the teacher.
        self.state = SubmissionState.MARKED
        self.sent_back_reason = ""
        self.save()
        return self

    def approve(self, user=None):
        """The class teacher releases the examiner's mark to the student."""
        self.state = SubmissionState.APPROVED
        self.approved_by = user
        self.date_approved = timezone.now()
        self.save()
        return self

    def send_back_to_examiner(self, user=None, reason=""):
        """The teacher returns the marking to the examiner to look at again."""
        self.state = SubmissionState.SENT_BACK
        self.sent_back_reason = reason
        self.save()
        return self

    def request_redo(self, user=None, reason=""):
        """A teacher asks this student to do this piece again."""
        self.state = SubmissionState.RETURNED
        self.redo_requested_by = user
        self.date_redo_requested = timezone.now()
        self.redo_reason = reason
        self.save()
        return self


class MarkLine(AuditModel):
    """
    One line of a submission's marks breakdown.

    A single total tells a student they got 14. A breakdown tells them
    which question lost the marks, which is the only part they can act
    on. The lines are free-text on purpose: a handout is a scanned paper,
    not a structured question bank, so the examiner names the parts the
    way the paper does.
    """

    submission = models.ForeignKey(
        "Submission", on_delete=models.PROTECT, related_name="mark_lines"
    )
    label = models.CharField(
        max_length=64,
        help_text="What the paper calls this part — Q1, Q2(a), Section B.",
    )
    out_of = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text="Marks available for this part.",
    )
    awarded = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text="Marks the student was given for it.",
    )
    comment = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Why, in a few words. The student reads this.",
    )
    source = models.CharField(
        max_length=16, choices=MarkSource.choices, default=MarkSource.EXAMINER,
        help_text="Who put this mark here. A human editing an autograded line "
                  "takes ownership of it, and the original stays in the audit trail.",
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")

    class Meta(AuditModel.Meta):
        db_table = "mark_line"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["submission"], name="mark_line_submiss_idx"),
        ]

    def __str__(self):
        return f"{self.label}: {self.awarded}/{self.out_of}"

    @property
    def lost(self):
        return (self.out_of or 0) - (self.awarded or 0)

    @property
    def full_marks(self):
        return self.out_of and self.awarded == self.out_of


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


# ---------------------------------------------------------------------
# The notice board
# ---------------------------------------------------------------------
class Notice(AuditModel):
    """
    Something the school puts in front of a class: an exam timetable, an
    exam syllabus, or a plain notice.

    Deliberately a file rather than structured rows. A quarterly timetable
    is produced once a term as a document, and re-typing it into the
    system would be work with no reader — nobody queries an exam timetable,
    they look at it. The structured route exists for anything that does
    need querying.

    An empty `grade` means every class sees it.
    """

    title = models.CharField(max_length=256)
    category = models.CharField(
        max_length=24, choices=NoticeCategory.choices,
        default=NoticeCategory.GENERAL,
    )
    grade = models.ForeignKey(
        Grade, on_delete=models.PROTECT, null=True, blank=True,
        related_name="notices",
        help_text="Which class it is for. Empty means all classes.",
    )
    academic_year = models.IntegerField(
        null=True, blank=True,
        help_text="The year it belongs to, so old timetables fall off the board.",
    )
    body = models.TextField(
        blank=True, default="",
        help_text="A line or two of context. The file is the notice; this is optional.",
    )
    published_from = models.DateTimeField(
        null=True, blank=True,
        help_text="Students see it from this moment. Empty means immediately.",
    )
    published_until = models.DateTimeField(
        null=True, blank=True,
        help_text="It drops off the board after this. Empty means it stays.",
    )
    posted_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, null=True, blank=True,
        related_name="notices_posted",
    )
    date_posted = models.DateTimeField(default=timezone.now)

    #: The timetable or syllabus itself, through the usual generic link.
    attachments = GenericRelation("AttachmentLink", related_query_name="notice")

    class Meta(AuditModel.Meta):
        db_table = "notice"
        ordering = ["-date_posted"]
        indexes = [
            models.Index(fields=["category"], name="notice_categor_idx"),
            models.Index(fields=["grade", "academic_year"], name="notice_grade_year_idx"),
        ]

    def __str__(self):
        return f"{self.get_category_display()} · {self.title}"

    @property
    def is_live(self):
        """On the board right now, decided from the clock rather than a flag."""
        now = timezone.now()
        if self.published_from and now < self.published_from:
            return False
        if self.published_until and now > self.published_until:
            return False
        return not self.voided

    def files(self):
        return [
            link.attachment for link in self.attachments.all()
            if not link.voided and link.attachment_id
        ]


# ---------------------------------------------------------------------
# Autograding — the seam to the marking service
# ---------------------------------------------------------------------
class AutogradeJob(AuditModel):
    """
    One request to have a submission marked by the autograding service.

    The service itself lives outside this codebase. This row is the seam:
    it records what was asked, what came back, and how sure the service
    was, so a mark can always be traced to the run that produced it.

    Nothing here marks anything. The service writes MarkLines with
    `source=AUTO`, and an examiner or teacher may overwrite any of them —
    which is the point. An autograded mark is a first draft, and the
    person who changes a line takes ownership of it while the job keeps
    the original for anyone who asks what the machine said.
    """

    submission = models.ForeignKey(
        Submission, on_delete=models.PROTECT, related_name="autograde_jobs"
    )
    status = models.CharField(
        max_length=16, choices=AutogradeStatus.choices,
        default=AutogradeStatus.QUEUED,
    )
    service_ref = models.CharField(
        max_length=128, blank=True, default="",
        help_text="The marking service's own id for this run, for tracing a "
                  "result back to its logs.",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    confidence = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="How sure the service was, if it says. Low confidence is a "
                  "reason to look, not a reason to reject.",
    )
    raw_response = models.JSONField(
        null=True, blank=True,
        help_text="Exactly what came back, kept verbatim so a disputed mark "
                  "can be checked against the source rather than the summary.",
    )
    error = models.TextField(
        blank=True, default="",
        help_text="Why it failed, if it did. A failed job is not a blocked "
                  "submission — the examiner simply marks it by hand.",
    )

    class Meta(AuditModel.Meta):
        db_table = "autograde_job"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status"], name="autograde_status_idx"),
            models.Index(fields=["submission"], name="autograde_submiss_idx"),
        ]

    def __str__(self):
        return f"{self.submission.code} · {self.get_status_display()}"

    @property
    def is_finished(self):
        return self.status in {AutogradeStatus.DONE, AutogradeStatus.FAILED,
                               AutogradeStatus.SKIPPED}
