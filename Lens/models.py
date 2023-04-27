from django.db import models

# Create your models here.


class LensOptions(models.Model):
    CompleteSetID = models.ForeignKey(
        'Order.CompleteSet', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    description = models.TextField()
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LensProperty(models.Model):
    CompleteSetID = models.ForeignKey(
        'Order.CompleteSet', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    description = models.TextField()
    add_on_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
