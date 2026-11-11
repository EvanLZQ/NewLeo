import os
import uuid

from django.core.files.storage import FileSystemStorage
from django.db import models

__all__ = ['PrescriptionInfo', 'PrescriptionPrism', 'PrescriptionUpload']


class PrescriptionInfo(models.Model):
    customer = models.ForeignKey('Customer.CustomerInfo', on_delete=models.CASCADE,
                                 related_name='prescription', null=True, blank=True)
    # Signed-out author: this browser session's owner token (server-side in
    # the Django session, never returned by the API). Rows with customer
    # NULL and no token predate the 2026-11-11 ownership fix and are not
    # readable by id except by staff. See Order/ownership.py.
    guest_token = models.CharField(
        max_length=64, blank=True, default='', db_index=True, editable=False)
    nickname = models.CharField(max_length=50, blank=True, null=True)
    pd_l = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pd_r = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sphere_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    sphere_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    cylinder_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    cylinder_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    axis_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    axis_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    add_l = models.DecimalField(
        blank=True, default=0, max_digits=5, decimal_places=2)
    add_r = models.DecimalField(
        blank=True, default=0, max_digits=5, decimal_places=2)
    base_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    base_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    photo = models.ImageField(
        upload_to='prescriptions/', null=True, blank=True,
        help_text="Reserved for the deferred 'upload a photo' prescription flow — "
                  "no upload UI or processing wired up yet. Not shipping this round; "
                  "kept here so adding the real feature later doesn't need a schema change.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Prescription'
        verbose_name_plural = 'Prescriptions'


class PrescriptionPrism(models.Model):
    """
    At most one row per prescription in practice — the form always writes
    (or replaces) a single combined row covering whichever of horizontal/
    vertical the customer actually filled in; the FK isn't unique=True only
    because nothing enforces that at the DB level, not because multiple
    rows are a meaningful state. See Prescription/serializer.py's
    PrescriptionSerializer._sync_prism (delete-then-recreate on every save).

    All 8 fields are optional: a customer may set only horizontal, only
    vertical, or (rarely) both. Direction is a plain string ("Up"/"Down" for
    vertical, "In"/"Out" for horizontal — see PrescriptionForm.tsx's
    verticalBaseOpts/horizontalBaseOpts), not a number — this was a
    DecimalField before, which couldn't have stored the real values that
    were ever actually collected client-side.
    """
    prescription = models.ForeignKey(
        'Prescription.PrescriptionInfo', on_delete=models.CASCADE, related_name='prism')
    horizontal_value_l = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    horizontal_direction_l = models.CharField(
        max_length=10, null=True, blank=True)
    horizontal_value_r = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    horizontal_direction_r = models.CharField(
        max_length=10, null=True, blank=True)
    vertical_value_l = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    vertical_direction_l = models.CharField(
        max_length=10, null=True, blank=True)
    vertical_value_r = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    vertical_direction_r = models.CharField(
        max_length=10, null=True, blank=True)

    class Meta:
        verbose_name = 'Prism'
        verbose_name_plural = 'Prism'


class PrivateUploadStorage(FileSystemStorage):
    """Files under settings.PRIVATE_MEDIA_ROOT, read at call time.

    PRIVATE_MEDIA_ROOT is outside MEDIA_ROOT, nginx does not mount it, and
    this storage has no URL (``url()`` raises), so a file here can only be
    read through the authenticated download view
    (Prescription.views.prescription_upload_file).
    """

    def __init__(self):
        super().__init__(file_permissions_mode=0o600, directory_permissions_mode=0o700)

    @property
    def base_location(self):
        from django.conf import settings
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Prescription uploads are private and have no public URL.")


def private_upload_storage():
    return PrivateUploadStorage()


def prescription_upload_path(instance, filename):
    """<PRIVATE_MEDIA_ROOT>/prescription_uploads/YYYY/MM/<random hex>.<ext>

    The shopper's file name is kept in `original_name` only. The stored name
    is random so the URL can't be guessed from the upload id or the name.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"prescription_uploads/{instance.uploaded_at_path()}/{uuid.uuid4().hex}{ext}"


class PrescriptionUpload(models.Model):
    """A photo or PDF of a paper prescription, uploaded on the lens page.

    Created before the cart item exists (the shopper uploads on the
    prescription step and adds to cart later), then linked from
    CompleteSet.prescription_upload. Only the uploader (same account, or the
    same signed-out session) can attach it; it is stored privately and read
    only through the authenticated download view.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.SET_NULL,
        related_name='prescription_uploads', null=True, blank=True)
    # Signed-out uploader: this browser session's owner token (server-side,
    # never returned by the API). See Order/ownership.py.
    guest_token = models.CharField(
        max_length=64, blank=True, default='', db_index=True, editable=False)
    file = models.FileField(
        upload_to=prescription_upload_path, storage=private_upload_storage,
        max_length=255)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField(help_text="Bytes")
    created_at = models.DateTimeField(auto_now_add=True)

    def uploaded_at_path(self):
        from django.utils import timezone
        now = self.created_at or timezone.now()
        return now.strftime("%Y/%m")

    @property
    def is_pdf(self):
        return self.content_type == "application/pdf"

    def __str__(self):
        return self.original_name or str(self.id)

    class Meta:
        verbose_name = 'Prescription upload'
        verbose_name_plural = 'Prescription uploads'
        ordering = ['-created_at']
