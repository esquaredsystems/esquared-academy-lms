"""Create the built-in question and student attribute types."""

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


def ensure_attribute_types(user):
    """Create or update the built-in attribute types for a superuser."""
    with transaction.atomic():
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
            else:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()

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
            else:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
