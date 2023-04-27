from django.db import models


class PrescriptionInfo(models.Model):
    pd_l = models.DecimalField(max_digits=5, decimal_places=2)
    pd_r = models.DecimalField(max_digits=5, decimal_places=2)
    sphere_l = models.DecimalField(max_digits=5, decimal_places=2)
    sphere_r = models.DecimalField(max_digits=5, decimal_places=2)
    cylinder_l = models.DecimalField(max_digits=5, decimal_places=2)
    cylinder_r = models.DecimalField(max_digits=5, decimal_places=2)
    axis_l = models.IntegerField(blank=True)
    axis_r = models.IntegerField(blank=True)
    prism_l = models.DecimalField(max_digits=5, decimal_places=2)
    prism_r = models.DecimalField(max_digits=5, decimal_places=2)
    base_l = models.DecimalField(max_digits=5, decimal_places=2)
    base_r = models.DecimalField(max_digits=5, decimal_places=2)
    nv_add = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PrescriptionPrism(models.Model):
    PrescriptionID = models.ForeignKey(
        'PrescriptionInfo', on_delete=models.CASCADE)
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
