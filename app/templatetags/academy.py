"""
Template filters shared by the admin pages.

`shorten` is the same 48-character rule the list columns use, so a name
truncated in a table and the same name truncated in a panel agree.
"""

from django import template

from ..columns import shorten as shorten_text

register = template.Library()


@register.filter(name="shorten")
def shorten(value):
    """First 45 characters and an ellipsis of three dots, past 48."""
    return shorten_text(value)
