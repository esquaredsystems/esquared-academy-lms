"""
Where uploaded files live, and what kind each one is.

Everything lands under one root — `MEDIA_ROOT`, set by `MEDIA_ROOT` in
.env — in a flat directory per kind:

    <media root>/
        text/      documents and anything readable as text, PDFs included
        audio/
        video/
        picture/
        other/
        _incoming/ chunks of uploads still in progress, never served

Stored names are the attachment's uuid plus the original extension, so two
files called "diagram.png" never collide and a stored name leaks nothing
about the paper it belongs to. The original filename is kept on the row.
"""

import hashlib
import os

from django.db import models

CHUNK_READ_SIZE = 1024 * 1024  # 1 MiB, for checksums and copies


class FileKind(models.TextChoices):
    TEXT = "text", "Text and documents"
    AUDIO = "audio", "Audio"
    VIDEO = "video", "Video"
    PICTURE = "picture", "Picture"
    OTHER = "other", "Other"


#: Document types that are not text/* but belong with the readable material.
DOCUMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rtf",
    "application/json",
    "application/xml",
    "application/epub+zip",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
}

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf",
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".epub", ".odt", ".ods",
}

PICTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff", ".heic"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


def classify(mime_type="", filename=""):
    """
    Decide a file's kind from its MIME type, falling back to its extension.

    Browsers send an empty or wrong MIME type often enough that the
    extension has to be a real fallback rather than a formality.
    """
    mime = (mime_type or "").split(";")[0].strip().lower()

    if mime.startswith("image/"):
        return FileKind.PICTURE
    if mime.startswith("audio/"):
        return FileKind.AUDIO
    if mime.startswith("video/"):
        return FileKind.VIDEO
    if mime.startswith("text/") or mime in DOCUMENT_TYPES:
        return FileKind.TEXT

    ext = os.path.splitext(filename or "")[1].lower()
    if ext in PICTURE_EXTENSIONS:
        return FileKind.PICTURE
    if ext in AUDIO_EXTENSIONS:
        return FileKind.AUDIO
    if ext in VIDEO_EXTENSIONS:
        return FileKind.VIDEO
    if ext in DOCUMENT_EXTENSIONS:
        return FileKind.TEXT
    return FileKind.OTHER


def attachment_path(instance, filename):
    """`<kind>/<uuid><ext>` — the flat, kind-first hierarchy."""
    ext = os.path.splitext(filename)[1].lower()
    return f"{instance.kind}/{instance.uuid}{ext}"


def sha256_of(file_obj):
    """Checksum a file-like object without loading it into memory."""
    digest = hashlib.sha256()
    file_obj.seek(0)
    for block in iter(lambda: file_obj.read(CHUNK_READ_SIZE), b""):
        digest.update(block)
    file_obj.seek(0)
    return digest.hexdigest()


def human_size(num_bytes):
    """1536 -> '1.5 KB'. For admin columns and API payloads."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# ---------------------------------------------------------------------
# Person photos
#
# Teacher and student portraits live beside every other picture, under
# picture/, and are named after the row's uuid like any other upload.
# Two rules govern them, in this order:
#
#   1. the image must be square — width equal to height;
#   2. the file must be under 100 KB.
#
# Square comes first because it is the rule that decides whether the
# picture can be shown at all: every avatar in the interface is drawn in
# a square (or a circle inscribed in one), and a portrait that is not
# square would be cropped by the browser without anyone choosing what to
# cut. Size comes second, and is checked only once the shape is right, so
# a person is told to crop before being told to compress.
# ---------------------------------------------------------------------

#: Second rule: the ceiling on a stored portrait.
PHOTO_MAX_BYTES = 100 * 1024

PHOTO_HELP = (
    "Square picture — the width must equal the height — and under 100 KB."
)


def person_photo_path(instance, filename):
    """`picture/<uuid><ext>`: portraits sit with the other pictures."""
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"{FileKind.PICTURE}/{instance.uuid}{ext}"


def photo_dimensions(value):
    """
    (width, height) of an uploaded or stored image, or None.

    Reads through Pillow rather than trusting the browser, and leaves the
    file rewound so the storage backend can still save it afterwards.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        position = value.tell()
    except (AttributeError, ValueError, OSError):
        position = 0
    try:
        value.seek(0)
        with Image.open(value) as image:
            return image.size
    except (UnidentifiedImageError, OSError, ValueError, AttributeError):
        return None
    finally:
        try:
            value.seek(position)
        except (AttributeError, ValueError, OSError):
            pass


def validate_person_photo(value):
    """
    Square first, then size — the two rules, applied in that order.

    Raised one at a time on purpose: being told to crop and compress at
    once, when cropping changes the size anyway, helps nobody.
    """
    from django.core.exceptions import ValidationError

    size = photo_dimensions(value)
    if size is None:
        raise ValidationError("That file could not be read as an image.")

    width, height = size
    if width != height:
        raise ValidationError(
            "The picture must be square: this one is %(width)s by %(height)s "
            "pixels. Crop it to a square and upload it again.",
            code="not_square",
            params={"width": width, "height": height},
        )

    file_size = getattr(value, "size", None)
    if file_size is not None and file_size > PHOTO_MAX_BYTES:
        raise ValidationError(
            "The picture must be under %(limit)s: this one is %(actual)s.",
            code="too_large",
            params={
                "limit": human_size(PHOTO_MAX_BYTES),
                "actual": human_size(file_size),
            },
        )
