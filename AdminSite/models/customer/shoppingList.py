from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# from ..product import ProductInfo
# from .customerInfo import CustomerInfo


class ShoppingList(models.Model):
    customer = models.ForeignKey('CustomerInfo', on_delete=models.CASCADE)
    product = models.ForeignKey(
        'AdminSite.ProductInfo', on_delete=models.CASCADE)
    quantity = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])
    list_type = models.CharField(max_length=30,
                                 choices=[('SHOPPINGCART', 'Shopping Cart'), ('WISHLIST', 'Wish List')])

    class Meta:
        db_table = 'ShoppingList'
        verbose_name = 'Shopping List'
        verbose_name_plural = 'Shopping Lists'
