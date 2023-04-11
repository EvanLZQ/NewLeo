from django.db import models

from ..product import ProductInfo
from .order_line_item import OrderLineItem


class OrderInfo(models.Model):
    product = models.ManyToManyField(ProductInfo, through=OrderLineItem)
    email = models.EmailField()
    order_number = models.CharField(max_length=20)
    order_status = models.CharField(choices=['Null', 'Processing', 'Shipped',
                                             'Delivered', 'Complete', 'Canceled', 'Refund'], default='Processing')
    refound_status = models.CharField(max_length=20, blank=True)
    refound_amount = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True)
    payment_status = models.CharField(
        choices=['Unpaid', 'Paid', 'Processing', 'Null'], default='Unpaid')
    payment_type = models.CharField(max_length=20, null=True)
    # TODO email model
    # email_send_list
    order_device = models.CharField(
        choices=['Windows', 'Mac OS', 'Android', 'IOS', 'Unknown'], default='Unknown')
    store_credit_used = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    store_credit_gained = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    shipping_company = models.CharField(max_length=50, blank=True)
    tracking_number = models.CharField(max_length=50, blank=True)
    shipping_cost = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    accessory_total = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    sub_total = models.DecimalField(max_digits=6, decimal_places=2)
    total_amount = models.DecimalField(max_digits=6, decimal_places=2)
    comment = models.TextField()
    issue_order = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
