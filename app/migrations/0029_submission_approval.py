import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0028_markline"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="approved_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="submissions_approved", to=settings.AUTH_USER_MODEL,
                help_text="The teacher who released this to the student.",
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="date_approved",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="submission",
            name="sent_back_reason",
            field=models.CharField(
                blank=True, default="", max_length=255,
                help_text="Why the teacher returned this to the examiner to re-check.",
            ),
        ),
        migrations.AlterField(
            model_name="submission",
            name="state",
            field=models.CharField(
                choices=[
                    ("submitted", "Waiting for the examiner"),
                    ("grading", "Being marked"),
                    ("marked", "Checked — waiting for teacher approval"),
                    ("sent_back", "Sent back to the examiner"),
                    ("approved", "Approved — released to the student"),
                    ("returned", "Sent back to the student to redo"),
                    ("accepted", "Accepted"),
                    ("rejected", "Rejected — unreadable"),
                ],
                default="submitted", max_length=16,
            ),
        ),
    ]
