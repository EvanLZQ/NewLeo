"""Validation for prescription photo / PDF uploads (2026-11-11 QA, issue 1).

Rules:
  * Allowed: JPEG, PNG, WEBP images and PDF.
  * Max size: 10 MB (PRESCRIPTION_UPLOAD_MAX_BYTES).
  * The type is decided from the file's first bytes, not from the
    extension or the browser's Content-Type, and the extension must agree.
  * Images must open in Pillow; PDFs must start with %PDF- and contain %%EOF.
"""
from django.conf import settings

ALLOWED = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
    "application/pdf": (".pdf",),
}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class UploadRejected(Exception):
    pass


def max_bytes():
    return int(getattr(settings, "PRESCRIPTION_UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES))


def sniff(head):
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def validate_upload(upload):
    """Return the detected content type, or raise UploadRejected."""
    if upload is None:
        raise UploadRejected("Choose a photo or PDF of your prescription.")
    limit = max_bytes()
    if upload.size == 0:
        raise UploadRejected("The file is empty.")
    if upload.size > limit:
        raise UploadRejected(
            f"The file is too large. The limit is {limit // (1024 * 1024)} MB.")
    name = (upload.name or "").lower()
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    kind = sniff(head)
    if kind is None:
        raise UploadRejected("Upload a JPG, PNG, WEBP image or a PDF.")
    if not name.endswith(ALLOWED[kind]):
        raise UploadRejected("The file name doesn't match its type. Upload a JPG, PNG, WEBP image or a PDF.")
    if kind == "application/pdf":
        upload.seek(max(0, upload.size - 2048))
        tail = upload.read()
        upload.seek(0)
        if b"%%EOF" not in tail:
            raise UploadRejected("This PDF looks damaged. Try saving it again or upload a photo.")
    else:
        from PIL import Image
        try:
            with Image.open(upload) as img:
                img.verify()
        except Exception:
            raise UploadRejected("This image can't be opened. Try another photo.")
        finally:
            upload.seek(0)
    return kind
