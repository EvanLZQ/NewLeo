from django.db import models

from ..address import Address
from .orderInfo import OrderInfo


class OrderHasAddress(models.Model):
    AddressID = models.ForeignKey(Address, on_delete=models.CASCADE)
    OrderID = models.ForeignKey(OrderInfo, on_delete=models.CASCADE)
