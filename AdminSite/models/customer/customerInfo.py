from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

# from ..product import ProductInfo
# from .shoppingList import ShoppingList


class CustomerInfo(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=30)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = PhoneNumberField(blank=True)
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    account_is_active = models.BooleanField(default=True)
    gender = models.CharField(max_length=15, choices=[
                              ("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")], blank=True)
    birth_date = models.DateField(blank=True)
    icon_url = models.CharField(max_length=100, blank=True)
    store_credit = models.IntegerField(default=0)
    level = models.IntegerField(default=0)
    wish_list = models.ManyToManyField(
        'AdminSite.ProductInfo', through='ShoppingList')
    # TODO address model
    # address = models.ForeignKey()
    in_blacklist = models.BooleanField(default=False)
    # TODO payment model
    # payment_method = models.ManyToManyField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)