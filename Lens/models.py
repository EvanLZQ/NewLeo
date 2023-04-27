from django.db import models

# Create your models here.
__all__ = ['LensOptions', 'LensProperty']


class LensOptions(models.Model):
    completeSetID = models.ForeignKey(
        'Order.CompleteSet', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    description = models.TextField()
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LensProperty(models.Model):
    completeSetID = models.ForeignKey(
        'Order.CompleteSet', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    description = models.TextField()
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
