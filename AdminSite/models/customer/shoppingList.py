from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from ..product import ProductInfo
from .customerInfo import CustomerInfo


class ShoppingList(models.Model):
    customer = models.ForeignKey(CustomerInfo, on_delete=models.CASCADE)
    product = models.ForeignKey(ProductInfo, on_delete=models.CASCADE)
    quantity = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])
    list_type = models.CharField(choices=['Shopping Cart', 'Wish List'])
