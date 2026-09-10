from django.db import models

__all__ = ['PrescriptionInfo', 'PrescriptionPrism']


class PrescriptionInfo(models.Model):
    customer = models.ForeignKey('Customer.CustomerInfo', on_delete=models.CASCADE,
                                 related_name='prescription', null=True, blank=True)
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
