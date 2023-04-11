from django.db import models

# from .orderInfo import OrderInfo


class OrderTax(models.Model):
    OrderID = models.ForeignKey(
        'AdminSite.OrderInfo', on_delete=models.CASCADE)
    tax_number = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=5, decimal_places=2)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    hst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    qst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
