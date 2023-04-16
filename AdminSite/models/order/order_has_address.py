from django.db import models

# from ..address import Address
# from models.address import Address
# from .orderInfo import OrderInfo


class OrderHasAddress(models.Model):
    AddressID = models.ForeignKey(
        'AdminSite.Address', on_delete=models.CASCADE)
    OrderID = models.ForeignKey(
        'AdminSite.OrderInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'order_has_address'
