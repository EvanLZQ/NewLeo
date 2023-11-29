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
    axis_l = models.IntegerField(blank=True, default=0)
    axis_r = models.IntegerField(blank=True, default=0)
    add_l = models.DecimalField(
        blank=True, default=0, max_digits=5, decimal_places=2)
    add_r = models.DecimalField(
        blank=True, default=0, max_digits=5, decimal_places=2)
    base_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    base_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Prescription'
        verbose_name_plural = 'Prescriptions'


class PrescriptionPrism(models.Model):
    prescription = models.ForeignKey(
        'Prescription.PrescriptionInfo', on_delete=models.CASCADE, related_name='prism')
    horizontal_value_l = models.DecimalField(max_digits=5, decimal_places=2)
    horizontal_direction_l = models.DecimalField(
        max_digits=5, decimal_places=2)
    horizontal_value_r = models.DecimalField(max_digits=5, decimal_places=2)
    horizontal_direction_r = models.DecimalField(
        max_digits=5, decimal_places=2)
    vertical_value_l = models.DecimalField(max_digits=5, decimal_places=2)
    vertical_direction_l = models.DecimalField(max_digits=5, decimal_places=2)
    vertical_value_r = models.DecimalField(max_digits=5, decimal_places=2)
    vertical_direction_r = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = 'Prism'
        verbose_name_plural = 'Prism'
