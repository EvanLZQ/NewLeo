from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from .orderInfo import OrderInfo
from ..product import ProductInfo


class OrderLineItem(models.Model):
    ProductID = models.ForeignKey(ProductInfo, on_delete=models.CASCADE)
    OrderID = models.ForeignKey(OrderInfo, on_delete=models.CASCADE)
    quantity = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(99)], default=0)
