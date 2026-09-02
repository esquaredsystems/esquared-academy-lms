"""
Column truncation for change lists.

Long names wreck a table: one 200-character topic title pushes every other
column off the screen. Every text column in every list is therefore cut to
48 characters — 45 plus an ellipsis — with the full value on hover.

Only text is touched. Dates, numbers, booleans and the columns that build
their own markup (the indented topic tree, the attachment thumbnails) are
passed through untouched, so nothing loses its icon or its formatting.
"""

from django.contrib.admin.utils import lookup_field
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.html import format_html
from django.utils.safestring import SafeString

#: Longest a column may render.
MAX_LENGTH = 48

#: How much of it is the value itself; the rest is the ellipsis.
KEEP = 45

#: Field types whose values are prose and may be cut.
TEXT_FIELDS = (
    models.CharField,
    models.TextField,
    models.EmailField,
    models.URLField,
    models.SlugField,
)

#: Related fields render as the target's __str__, which is a name too.
RELATION_FIELDS = (models.ForeignKey, models.OneToOneField)


def shorten(value):
    """'A very long title…' — or the value unchanged if it already fits."""
    if not isinstance(value, str) or len(value) <= MAX_LENGTH:
        return value
    return value[:KEEP].rstrip() + "..."


class TruncatedColumnsMixin:
    """
    Wraps every list_display entry so long text is cut.

    The wrapper keeps the original's sorting, heading and boolean icon, so
    a ModelAdmin using it behaves exactly as before apart from the width.
    """

    truncate_columns = True

    def get_list_display(self, request):
        display = super().get_list_display(request)
        if not self.truncate_columns:
            return display
        return tuple(self._truncating_column(name) for name in display)

    def _truncating_column(self, name):
        if callable(name):
            return name

        original = getattr(self, name, None)
        # Columns that render their own HTML keep it — truncating markup
        # would break it, and they are short by construction.
        if getattr(original, "boolean", False):
            return name

        try:
            field = self.model._meta.get_field(name)
        except Exception:
            field = None

        # A concrete non-text, non-relation field renders through Django's
        # own formatting (dates, decimals, booleans). Leave it alone.
        if field is not None and not isinstance(field, TEXT_FIELDS + RELATION_FIELDS):
            return name

        admin_ref = self

        def column(obj, _name=name):
            try:
                _f, _attr, value = lookup_field(_name, obj, admin_ref)
            except (AttributeError, ValueError, ObjectDoesNotExist):
                return admin_ref.get_empty_value_display()

            if isinstance(value, SafeString):
                # A column that builds its own markup truncates its own
                # text — see TopicAdmin.indented_name.
                return value
            if value is None or isinstance(value, bool):
                return value
            if not isinstance(value, str):
                if isinstance(getattr(value, "_meta", None), object) and hasattr(value, "pk"):
                    value = str(value)          # a related object: show its name
                else:
                    return value
            if len(value) <= MAX_LENGTH:
                return value
            return format_html('<span title="{}">{}</span>', value, shorten(value))

        column.short_description = self._column_label(name, original, field)
        column.admin_order_field = getattr(
            original, "admin_order_field", name if field is not None else None
        )
        column.__name__ = name
        return column

    @staticmethod
    def _column_label(name, original, field):
        label = getattr(original, "short_description", None)
        if label:
            return label
        if field is not None:
            return field.verbose_name
        return name.replace("_", " ")
