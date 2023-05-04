from django.db import models

# Create your models here.


class SupplierInfo(models.Model):
    name = models.CharField(max_length=100)
    website = models.URLField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'SupplierInfo'
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
