"""
Who is making the change.

The audit block is self-controlled: `created_by` and `date_created` are
stamped once at insert and can never change, and `changed_by` /
`date_changed` are stamped on every update. Neither is passed in by the
caller, so the model layer needs to know who is acting. That is what this
holds: the request's user, in a context variable, set by the middleware
below and read by `AuditModel.save()`.

A context variable rather than thread-local storage, so it behaves under
async views as well as threads. Outside a request — a management command,
a shell, a test — it is simply empty, and callers may pass `created_by`
explicitly instead.
"""

import contextvars

_current_user = contextvars.ContextVar("audit_current_user", default=None)


def get_current_user():
    """The user for the request in flight, or None outside a request."""
    user = _current_user.get()
    return user if getattr(user, "is_authenticated", False) else None


def set_current_user(user):
    """Set the acting user. Returns a token for `reset_current_user`."""
    return _current_user.set(user)


def reset_current_user(token):
    _current_user.reset(token)


class CurrentUserMiddleware:
    """Publishes request.user for the duration of the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            reset_current_user(token)
