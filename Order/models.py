from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
# Create your models here.

__all__ = ['OrderInfo', 'OrderTax',
           'OrderImage', 'OrderUpdates', 'CompleteSet']


class OrderInfo(models.Model):
    product = models.ManyToManyField(
        'Product.ProductInfo', through='Order.OrderLineItem', blank=True)
    email = models.EmailField()
    order_number = models.CharField(max_length=20)
    order_status = models.CharField(max_length=50,
                                    choices=[('NULL', 'Null'), ('PROCESSING', 'Processing'), ('SHIPPED', 'Shipped'),
                                             ('DELIVERED', 'Delivered'), ('COMPLETE', 'Complete'), ('CANCELED', 'Canceled'), ('REFUND', 'Refund')], default='PROCESSING')
    refound_status = models.CharField(max_length=20, blank=True)
    refound_amount = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True)
    payment_status = models.CharField(max_length=50,
                                      choices=[('UNPAID', 'Unpaid'), ('PAID', 'Paid'), ('PROCESSING', 'Processing'), ('NULL', 'Null')], default='UNPAID')
    payment_type = models.CharField(max_length=20, null=True)
    # TODO email model
    # email_send_list
    order_device = models.CharField(max_length=50,
                                    choices=[('WINDOWS', 'Windows'), ('MACOS', 'Mac OS'), ('ANDROID', 'Android'), ('IOS', 'ios'), ('UNKNOWN', 'Unknown')], default='UNKNOWN')
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

    class Meta:
        db_table = 'OrderInfo'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'


class OrderTax(models.Model):
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    tax_number = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=5, decimal_places=2)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    hst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    qst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'OrderTax'
        verbose_name = 'Order Tax'
        verbose_name_plural = 'Order Tax'


class OrderImage(models.Model):
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    image_type = models.CharField(max_length=20)
    name = models.CharField(max_length=20)
    path = models.URLField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'OrderImage'
        verbose_name = 'Order Image'
        verbose_name_plural = 'Order Images'


class OrderUpdates(models.Model):
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    details = models.TextField()
    by = models.CharField(max_length=50)

    class Meta:
        db_table = 'OrderUpdates'
        verbose_name = 'Order Update'
        verbose_name_plural = 'Order Updates'


# Transaction tables:

class OrderHasAddress(models.Model):
    AddressID = models.ForeignKey(
        'General.Address', on_delete=models.CASCADE)
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'order_has_address'


class OrderLineItem(models.Model):
    ProductID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    quantity = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(99)], default=0)

    class Meta:
        db_table = 'order_line_item'


class CompleteSet(models.Model):
    OrderID = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    ProductID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    usage = models.CharField(max_length=100)
    color = models.CharField(max_length=100)
    index = models.CharField(max_length=100)
    customization = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Complete Set'
        verbose_name_plural = 'Complete Sets'


class OrderCompletePrescription(models.Model):
    CompleteSetID = models.ForeignKey('CompleteSet', on_delete=models.CASCADE)
    PrescriptionID = models.ForeignKey(
        'Prescription.PrescriptionInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'order_complete_prescription'
