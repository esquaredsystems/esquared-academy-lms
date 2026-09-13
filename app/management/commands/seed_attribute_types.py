"""
Seed the initial attribute types: the properties QuestionAttribute and
StudentAttribute rows can hold values for.

    python manage.py seed_attribute_types
    python manage.py seed_attribute_types --dry-run

Without this, a fresh database has the attribute-type/attribute tables but
nothing in them — no way to record a question's answer key or a student's
optional fields until someone adds the types by hand. This command creates
the types that replace what used to be plain columns (BinaryConfig,
NumericConfig, Student.national_id_type, Student.guardian_contact_2), so a
fresh install behaves like the old schema on day one. Adding another
attribute type later — for a school-specific field nobody has asked for
yet — is a row through the admin, not a change to this file.

Idempotent: matched on short_name (its stable key), so running it again
after editing a label or a datatype_config here updates the existing row
in place rather than duplicating it.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models

#: (short_name, name, datatype, datatype_config, applies_to, description)
QUESTION_ATTRIBUTE_TYPES = [
    (
        "binary_expected_value", "Expected value", models.AttributeDatatype.BOOLEAN,
        None, models.QuestionType.BINARY, "The correct answer. True means ticked.",
    ),
    (
        "binary_true_label", "True label", models.AttributeDatatype.TEXT,
        None, models.QuestionType.BINARY,
        "What the student sees instead of 'True' — Yes, Agree, Valid.",
    ),
    (
        "binary_false_label", "False label", models.AttributeDatatype.TEXT,
        None, models.QuestionType.BINARY, "The same for the other option.",
    ),
    (
        "binary_true_feedback", "True feedback", models.AttributeDatatype.TEXT,
        None, models.QuestionType.BINARY,
        "Shown when they answer true. Useful for explaining a common mistake.",
    ),
    (
        "numeric_expected_value", "Expected value", models.AttributeDatatype.DECIMAL,
        None, models.QuestionType.NUMERIC, "The correct number.",
    ),
    (
        "numeric_tolerance_type", "Tolerance type", models.AttributeDatatype.TEXT,
        "|".join(models.ToleranceType.values), models.QuestionType.NUMERIC,
        "absolute is a fixed amount either way; relative is a percentage; "
        "geometric scales with magnitude.",
    ),
    (
        "numeric_tolerance", "Tolerance", models.AttributeDatatype.DECIMAL,
        None, models.QuestionType.NUMERIC,
        "The size of that band. 0 demands the exact value.",
    ),
    (
        "numeric_partial_band", "Partial band", models.AttributeDatatype.DECIMAL,
        None, models.QuestionType.NUMERIC,
        "A wider band outside tolerance that still earns something.",
    ),
    (
        "numeric_partial_fraction", "Partial fraction", models.AttributeDatatype.DECIMAL,
        None, models.QuestionType.NUMERIC,
        "What that wider band earns, as a fraction of the mark — 0.5 for half.",
    ),
    (
        "numeric_unit", "Unit", models.AttributeDatatype.TEXT,
        None, models.QuestionType.NUMERIC, "The expected unit, where one is required.",
    ),
    (
        "numeric_unit_penalty", "Unit penalty", models.AttributeDatatype.DECIMAL,
        None, models.QuestionType.NUMERIC,
        "Fraction lost for the right number with the wrong unit.",
    ),
    (
        "numeric_significant_figures", "Significant figures", models.AttributeDatatype.INTEGER,
        None, models.QuestionType.NUMERIC, "Figures the answer is expected to. Optional.",
    ),
]

#: (short_name, name, datatype, datatype_config, description)
STUDENT_ATTRIBUTE_TYPES = [
    (
        "national_id_type", "National ID type", models.AttributeDatatype.TEXT,
        "cnic|b_form|passport",
        "Which document national_id came from — CNIC, B-Form or Passport.",
    ),
    (
        "guardian_contact_2", "Second guardian contact", models.AttributeDatatype.TEXT,
        None, "A second guardian number. Cambridge asks for two for candidates under 18.",
    ),
]


class Command(BaseCommand):
    help = "Create the initial QuestionAttributeType/StudentAttributeType rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        user = models.AppUser.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            raise CommandError(
                "No superuser to attribute the seed to. Run migrate (which creates "
                "one) first."
            )

        self.counts = {"question": [0, 0], "student": [0, 0]}

        try:
            with transaction.atomic():
                self._seed_question_types(user)
                self._seed_student_types(user)
                if dry_run:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING("\nDry run — nothing was written.\n"))

        self._report()

    def _seed_question_types(self, user):
        for order, (short_name, name, datatype, config, applies_to, description) in enumerate(
            QUESTION_ATTRIBUTE_TYPES, start=1
        ):
            defaults = {
                "name": name, "datatype": datatype, "datatype_config": config,
                "applies_to": applies_to, "description": description, "sort_order": order,
            }
            obj = models.QuestionAttributeType.objects.filter(short_name=short_name).first()
            if obj is None:
                models.QuestionAttributeType.objects.create(
                    short_name=short_name, created_by=user, **defaults
                )
                self.counts["question"][0] += 1
            else:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
                self.counts["question"][1] += 1

    def _seed_student_types(self, user):
        for order, (short_name, name, datatype, config, description) in enumerate(
            STUDENT_ATTRIBUTE_TYPES, start=1
        ):
            defaults = {
                "name": name, "datatype": datatype, "datatype_config": config,
                "description": description, "sort_order": order,
            }
            obj = models.StudentAttributeType.objects.filter(short_name=short_name).first()
            if obj is None:
                models.StudentAttributeType.objects.create(
                    short_name=short_name, created_by=user, **defaults
                )
                self.counts["student"][0] += 1
            else:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
                self.counts["student"][1] += 1

    def _report(self):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Attribute types"))
        for kind, (created, updated) in self.counts.items():
            self.stdout.write(f"  {kind:10} {created:3} created, {updated:3} updated")
        self.stdout.write("")


class _Rollback(Exception):
    pass
