from django.db import models

# from .customerInfo import CustomerInfo
# from ..address import Address


class CustomerSavedAddress(models.Model):
    CustomerID = models.ForeignKey(
        'AdminSite.CustomerInfo', on_delete=models.CASCADE)
    AddressID = models.ForeignKey(
        'AdminSite.Address', on_delete=models.CASCADE)
