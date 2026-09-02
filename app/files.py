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
