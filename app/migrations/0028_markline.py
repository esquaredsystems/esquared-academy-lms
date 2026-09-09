import django.db.models.deletion
import django.db.models.manager
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0027_submission_date_redo_requested_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarkLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("date_created", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("date_changed", models.DateTimeField(blank=True, editable=False, null=True)),
                ("voided", models.BooleanField(db_index=True, default=False)),
                ("active_flag", models.BooleanField(default=True, editable=False, help_text="True while the row is live, NULL once voided. Unique constraints include this column so that voided rows stop competing for the key: NULLs are distinct in a unique index on every backend, which is how soft deletion stays portable to MySQL, where partial indexes do not exist.", null=True)),
                ("date_voided", models.DateTimeField(blank=True, null=True)),
                ("void_reason", models.TextField(blank=True, null=True)),
                ("label", models.CharField(help_text="What the paper calls this part — Q1, Q2(a), Section B.", max_length=64)),
                ("out_of", models.DecimalField(decimal_places=2, default=0, help_text="Marks available for this part.", max_digits=6)),
                ("awarded", models.DecimalField(decimal_places=2, default=0, help_text="Marks the student was given for it.", max_digits=6)),
                ("comment", models.CharField(blank=True, default="", help_text="Why, in a few words. The student reads this.", max_length=255)),
                ("sort_order", models.IntegerField(default=0, verbose_name="sort")),
                ("changed_by", models.ForeignKey(blank=True, db_column="changed_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, db_column="created_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("voided_by", models.ForeignKey(blank=True, db_column="voided_by", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mark_lines", to="app.submission")),
            ],
            options={
                "db_table": "mark_line",
                "ordering": ["sort_order", "id"],
                "abstract": False,
                "base_manager_name": "all_objects",
                "indexes": [models.Index(fields=["submission"], name="mark_line_submiss_idx")],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
