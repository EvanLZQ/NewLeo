from django.db import models

# from .orderInfo import OrderInfo


class OrderImage(models.Model):
    OrderID = models.ForeignKey(
        'AdminSite.OrderInfo', on_delete=models.CASCADE)
    image_type = models.CharField(max_length=20)
    name = models.CharField(max_length=20)
    path = models.URLField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
