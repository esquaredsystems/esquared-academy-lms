"""
Generic attribute-type / attribute pattern, modeled on OpenMRS's
location / location_attribute_type / location_attribute.

An attributable entity keeps its structural columns — foreign keys,
workflow state, anything access.py or grading.py depends on — as real
columns. Optional, descriptive properties become rows here instead: one
AttributeType row names and types the property (once, by whoever
administers the school), and one Attribute row per entity instance holds
its value. Adding a new optional field from here on is a data change (add
an AttributeType row) rather than a schema change (a migration).

Values are always stored as text (`value_reference`) and resolved back to
a typed Python value through `AttributeDatatype` — the same shape as
OpenMRS's BaseAttributeType/BaseAttribute (a datatype + datatype config on
the type, a text value_reference on the attribute), simplified here to a
closed set of datatypes rather than pluggable classes, since nothing in
this codebase needs that generality yet.

Concrete pairs live in models.py, next to the entity they belong to, and
combine these abstract classes with AuditModel by multiple inheritance
(`class QuestionAttributeType(AuditModel, BaseAttributeType): ...`) —
these classes live here, separately from models.py, only to avoid a
circular import; they carry no audit fields of their own.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models


class AttributeDatatype(models.TextChoices):
    TEXT = "text", "Text"
    BOOLEAN = "boolean", "Yes/No"
    INTEGER = "integer", "Whole number"
    DECIMAL = "decimal", "Decimal number"
    DATE = "date", "Date"
    DATETIME = "datetime", "Date and time"


def to_python(datatype, raw):
    """The stored text, resolved to a real Python value. Blank passes through as None."""
    if raw is None or raw == "":
        return None
    if datatype == AttributeDatatype.TEXT:
        return raw
    if datatype == AttributeDatatype.BOOLEAN:
        return raw.strip().lower() in ("1", "true", "yes")
    if datatype == AttributeDatatype.INTEGER:
        return int(raw)
    if datatype == AttributeDatatype.DECIMAL:
        return Decimal(raw)
    if datatype == AttributeDatatype.DATE:
        return date.fromisoformat(raw)
    if datatype == AttributeDatatype.DATETIME:
        return datetime.fromisoformat(raw)
    raise ValueError(f"Unknown attribute datatype: {datatype!r}")


def to_storage(datatype, value):
    """A Python value, turned into the text `value_reference` stores. None -> ''."""
    if value is None:
        return ""
    if datatype == AttributeDatatype.TEXT:
        return str(value)
    if datatype == AttributeDatatype.BOOLEAN:
        return "true" if value else "false"
    if datatype in (AttributeDatatype.INTEGER, AttributeDatatype.DECIMAL):
        return str(value)
    if datatype in (AttributeDatatype.DATE, AttributeDatatype.DATETIME):
        return value.isoformat()
    raise ValueError(f"Unknown attribute datatype: {datatype!r}")


def validate_raw(datatype, raw, datatype_config=None):
    """
    Raise ValidationError if `raw` cannot be stored as `datatype`.

    For TEXT, a non-empty `datatype_config` is read as a '|'-separated
    allow-list (this is how a closed set of choices — e.g. the old
    Student.national_id_type — is expressed as an attribute: a TEXT
    attribute type with `datatype_config="cnic|b_form|passport"`, rather
    than a dedicated CHOICE datatype). Every other datatype ignores it.
    """
    try:
        to_python(datatype, raw)
    except (ValueError, InvalidOperation):
        raise ValidationError(
            "%(value)r is not a valid %(datatype)s value.",
            params={"value": raw, "datatype": datatype},
        )
    if datatype == AttributeDatatype.TEXT and datatype_config:
        allowed = [v.strip() for v in datatype_config.split("|") if v.strip()]
        if allowed and raw not in allowed:
            raise ValidationError(
                "%(value)r must be one of: %(allowed)s.",
                params={"value": raw, "allowed": ", ".join(allowed)},
            )


class BaseAttributeType(models.Model):
    """
    Abstract: the shared shape of every `<Entity>AttributeType`.

    One row per named, typed property an entity may carry — created by
    whoever administers the school, not by a migration. `short_name` is
    the stable key application code and imports look the attribute up by;
    `name`/`description` are what a person sees when adding one.
    """

    name = models.CharField(max_length=128)
    short_name = models.SlugField(
        max_length=64,
        help_text="The stable key code looks this attribute up by. Set once — changing "
                   "it orphans any existing values stored under the old key.",
    )
    description = models.TextField(null=True, blank=True)
    datatype = models.CharField(max_length=16, choices=AttributeDatatype.choices)
    datatype_config = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Datatype-specific configuration, e.g. a '|'-separated list of allowed "
                   "values for a constrained TEXT attribute. Not enforced by every datatype.",
    )
    min_occurs = models.PositiveSmallIntegerField(
        default=0, help_text="0 = optional. Not currently enforced by a DB constraint.",
    )
    max_occurs = models.PositiveSmallIntegerField(
        default=1, help_text="1 = single-valued, the normal case. Higher allows repeats.",
    )
    sort_order = models.IntegerField(default=0, verbose_name="sort")
    visible = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def python_value(self, raw):
        return to_python(self.datatype, raw)

    def storage_value(self, value):
        return to_storage(self.datatype, value)


class BaseAttribute(models.Model):
    """
    Abstract: the shared shape of every `<Entity>Attribute`.

    Concrete subclasses add their own `owner` FK (to the entity) and
    `attribute_type` FK (to that entity's AttributeType) — an abstract
    model can't declare a FK whose target differs per subclass. Storing
    and resolving the value lives here once, shared by every pair.
    """

    value_reference = models.TextField(blank=True, default="")

    class Meta:
        abstract = True

    def get_value(self):
        """The stored text, resolved through this attribute's type."""
        return self.attribute_type.python_value(self.value_reference)

    def set_value(self, value):
        """Store a Python value as this attribute's type dictates."""
        self.value_reference = self.attribute_type.storage_value(value)

    def clean(self):
        super().clean()
        if self.value_reference:
            validate_raw(
                self.attribute_type.datatype,
                self.value_reference,
                self.attribute_type.datatype_config,
            )

    def __str__(self):
        return f"{self.attribute_type.name} = {self.value_reference}"
