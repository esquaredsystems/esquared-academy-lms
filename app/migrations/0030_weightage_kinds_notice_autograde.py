"""
Weightage, paper kinds, the notice board, and the autograding seam.

Weight is not stored on a paper — it is resolved from the topic's
importance (`syllabus_topic.weight_pct`, which already exists) at read
time, so a teacher rates a topic once when planning the year and never
weighs an individual test. `weight_override` is only for the exception.
"""

import django.core.validators
import django.db.models.deletion
import django.db.models.manager
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models

AUDIT_FIELDS = [
    ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
    ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
    ("date_created", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
    ("date_changed", models.DateTimeField(blank=True, editable=False, null=True)),
    ("voided", models.BooleanField(db_index=True, default=False)),
    ("active_flag", models.BooleanField(default=True, editable=False, help_text="True while the row is live, NULL once voided. Unique constraints include this column so that voided rows stop competing for the key: NULLs are distinct in a unique index on every backend, which is how soft deletion stays portable to MySQL, where partial indexes do not exist.", null=True)),
    ("date_voided", models.DateTimeField(blank=True, null=True)),
    ("void_reason", models.TextField(blank=True, null=True)),
]

AUDIT_FKS = [
    ("changed_by", models.ForeignKey(blank=True, db_column="changed_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
    ("created_by", models.ForeignKey(blank=True, db_column="created_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
    ("voided_by", models.ForeignKey(blank=True, db_column="voided_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
]

AUDIT_MANAGERS = [
    ("objects", django.db.models.manager.Manager()),
    ("all_objects", django.db.models.manager.Manager()),
]


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0029_submission_approval"),
    ]

    operations = [
        # -- paper kinds and weight -------------------------------------
        migrations.AddField(
            model_name="handout",
            name="kind",
            field=models.CharField(
                choices=[
                    ("assignment", "Assignment"),
                    ("assessment", "Class assessment"),
                    ("mock", "Mock exam"),
                    ("quarterly", "Quarterly exam"),
                ],
                default="assignment",
                help_text="An assignment is set in class; the exam kinds are sat under supervision and are never shown to a class in advance.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="handout",
            name="weight_override",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True,
                help_text="Leave empty to inherit the topic's importance. Set it only for a paper that should count more or less than its topic.",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="weight override",
            ),
        ),
        migrations.AddField(
            model_name="handout",
            name="counts_toward_grade",
            field=models.BooleanField(
                default=True,
                help_text="Clear it for practice work that is marked but should not move the student's average.",
            ),
        ),
        # -- who put a mark there ---------------------------------------
        migrations.AddField(
            model_name="markline",
            name="source",
            field=models.CharField(
                choices=[
                    ("auto", "Autograder"),
                    ("examiner", "Examiner"),
                    ("teacher", "Teacher"),
                ],
                default="examiner",
                help_text="Who put this mark here. A human editing an autograded line takes ownership of it, and the original stays in the audit trail.",
                max_length=16,
            ),
        ),
        # -- the notice board -------------------------------------------
        migrations.CreateModel(
            name="Notice",
            fields=AUDIT_FIELDS + [
                ("title", models.CharField(max_length=256)),
                ("category", models.CharField(choices=[("exam_timetable", "Exam timetable"), ("exam_syllabus", "Exam syllabus"), ("general", "General notice")], default="general", max_length=24)),
                ("academic_year", models.IntegerField(blank=True, null=True, help_text="The year it belongs to, so old timetables fall off the board.")),
                ("body", models.TextField(blank=True, default="", help_text="A line or two of context. The file is the notice; this is optional.")),
                ("published_from", models.DateTimeField(blank=True, null=True, help_text="Students see it from this moment. Empty means immediately.")),
                ("published_until", models.DateTimeField(blank=True, null=True, help_text="It drops off the board after this. Empty means it stays.")),
                ("date_posted", models.DateTimeField(default=django.utils.timezone.now)),
            ] + AUDIT_FKS + [
                ("grade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="notices", to="app.grade", help_text="Which class it is for. Empty means all classes.")),
                ("posted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="notices_posted", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "notice",
                "ordering": ["-date_posted"],
                "abstract": False,
                "base_manager_name": "all_objects",
                "indexes": [
                    models.Index(fields=["category"], name="notice_categor_idx"),
                    models.Index(fields=["grade", "academic_year"], name="notice_grade_year_idx"),
                ],
            },
            managers=AUDIT_MANAGERS,
        ),
        # -- the autograding seam ---------------------------------------
        migrations.CreateModel(
            name="AutogradeJob",
            fields=AUDIT_FIELDS + [
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed"), ("skipped", "Skipped")], default="queued", max_length=16)),
                ("service_ref", models.CharField(blank=True, default="", max_length=128, help_text="The marking service's own id for this run, for tracing a result back to its logs.")),
                ("requested_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("confidence", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, help_text="How sure the service was, if it says. Low confidence is a reason to look, not a reason to reject.", validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("raw_response", models.JSONField(blank=True, null=True, help_text="Exactly what came back, kept verbatim so a disputed mark can be checked against the source rather than the summary.")),
                ("error", models.TextField(blank=True, default="", help_text="Why it failed, if it did. A failed job is not a blocked submission — the examiner simply marks it by hand.")),
            ] + AUDIT_FKS + [
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="autograde_jobs", to="app.submission")),
            ],
            options={
                "db_table": "autograde_job",
                "ordering": ["-requested_at"],
                "abstract": False,
                "base_manager_name": "all_objects",
                "indexes": [
                    models.Index(fields=["status"], name="autograde_status_idx"),
                    models.Index(fields=["submission"], name="autograde_submiss_idx"),
                ],
            },
            managers=AUDIT_MANAGERS,
        ),
    ]
