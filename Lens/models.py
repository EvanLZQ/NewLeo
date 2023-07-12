from django.db import models

__all__ = ['LensUsage', 'LensColor', 'LensCoating',
           'LensDensity', 'LensIndex']


class LensUsage(models.Model):
    name = models.CharField(max_length=50, default="Clear")
    description = models.TextField(blank=True)
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    image_url = models.CharField(max_length=4096, blank=True, default="")
    available_next_lvl = models.CharField(
        max_length=1024, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'LensUsage'
        verbose_name = 'Lens Usage'
        verbose_name_plural = 'Lens Usage'


class LensColor(models.Model):
    name = models.CharField(max_length=50, default="Clear")
    description = models.TextField(blank=True)
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    image_url = models.CharField(max_length=4096, blank=True, default="")
    available_colors = models.CharField(max_length=4096, default="")
    available_next_lvl = models.CharField(
        max_length=1024, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'LensColor'
        verbose_name = 'Lens Color'
        verbose_name_plural = 'Lens Color'


class LensDensity(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    image_url = models.CharField(max_length=4096, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'LensDensity'
        verbose_name = 'Lens Density'
        verbose_name_plural = 'Lens Density'


class LensCoating(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    image_url = models.CharField(max_length=4096, blank=True, default="")
    available_next_lvl = models.CharField(
        max_length=1024, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'LensCoating'
        verbose_name = 'Lens Coating'
        verbose_name_plural = 'Lens Coating'


class LensIndex(models.Model):
    name = models.CharField(max_length=50, default="Standard(1.56)")
    description = models.TextField(blank=True)
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    image_url = models.CharField(max_length=4096, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'LensIndex'
        verbose_name = 'Lens Index'
        verbose_name_plural = 'Lens Index'


# class LensOptions(models.Model):
#     name = models.CharField(max_length=50)
#     description = models.TextField(blank=True)
#     add_on_price = models.DecimalField(
#         max_digits=5, decimal_places=2, default=0)
#     image_url = models.CharField(max_length=4096, blank=True, default="")
#     available_next_lvl = models.CharField(
#         max_length=1024, blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return self.name

#     class Meta:
#         db_table = 'LensOptions'
#         verbose_name = 'Lens Option'
#         verbose_name_plural = 'Lens Options'
