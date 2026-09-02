"""
Give every existing row a uuid.

Migration 0004 adds the column nullable, this fills it, and 0006 makes it
unique and required. Three steps rather than one because a single AddField
computes the Python default once and writes the same uuid to every row,
which then fails the unique index.
"""

import uuid

from django.db import migrations

AUDITED_MODELS = [
    "AppUser", "Grade", "Student", "Teacher", "Enrolment",
    "Subject", "Topic", "Syllabus", "SyllabusTopic", "StudentSubject",
    "TeachingAssignment", "EvaluationPrompt", "PromptVersion", "Question",
    "BinaryConfig", "NumericConfig", "QuestionPaper", "PaperVersion",
    "PaperItem", "StudentCohort", "CohortMembership", "PaperAssignment",
    "Attempt", "Answer", "Evaluation", "RetentionPolicy",
]


def populate(apps, schema_editor):
    for name in AUDITED_MODELS:
        model = apps.get_model("app", name)
        rows = list(model.objects.filter(uuid__isnull=True).only("pk"))
        for row in rows:
            row.uuid = uuid.uuid4()
        if rows:
            model.objects.bulk_update(rows, ["uuid"], batch_size=500)


def noop(apps, schema_editor):
    """Reversing 0006 makes the column nullable again; nothing to undo here."""


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0004_add_uuid_column"),
    ]

    operations = [
        migrations.RunPython(populate, noop),
    ]
