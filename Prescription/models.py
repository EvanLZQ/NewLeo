from django.db import models

__all__ = ['PrescriptionInfo', 'PrescriptionPrism']


class PrescriptionInfo(models.Model):
    pd_l = models.DecimalField(max_digits=5, decimal_places=2)
    pd_r = models.DecimalField(max_digits=5, decimal_places=2)
    sphere_l = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    sphere_r = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    cylinder_l = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True)
    cylinder_r = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True)
    axis_l = models.IntegerField(blank=True)
    axis_r = models.IntegerField(blank=True)
    base_l = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    base_r = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    nv_add = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Presctiption'
        verbose_name_plural = 'Presctiptions'


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
