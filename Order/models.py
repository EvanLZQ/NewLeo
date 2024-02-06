from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Sum
# Create your models here.

__all__ = ['OrderInfo', 'OrderTax',
           'OrderImage', 'OrderUpdates', 'CompleteSet']


class OrderInfo(models.Model):
    product = models.ManyToManyField(
        'Product.ProductInstance', through='Order.OrderLineItem', blank=True)
    email = models.EmailField()
    customer = models.ForeignKey('Customer.CustomerInfo', null=True,
                                 on_delete=models.SET_NULL, blank=True, related_name='order')
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
    address = models.ForeignKey(
        'General.Address', null=True, on_delete=models.SET_NULL)
    issue_order = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.order_number

    def calculate_sub_total(self):
        # Calculate the sum of sub_total of all related CompleteSet instances
        total = CompleteSet.objects.filter(order=self).aggregate(
            Sum('sub_total'))['sub_total__sum']
        return total if total is not None else 0

    def save(self, *args, **kwargs):
        self.sub_total = self.calculate_sub_total()
        super(OrderInfo, self).save(*args, **kwargs)

    class Meta:
        db_table = 'OrderInfo'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'


class OrderTax(models.Model):
    order = models.ForeignKey(
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
    order = models.ForeignKey(
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
    order = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    details = models.TextField()
    by = models.CharField(max_length=50)

    class Meta:
        db_table = 'OrderUpdates'
        verbose_name = 'Order Update'
        verbose_name_plural = 'Order Updates'


class OrderPayment(models.Model):
    PAYMENT_GATEWAYS = [
        ('paypal', 'PayPal'),
        ('ocean_payment', 'Ocean Payment'),
        # ... other gateways
    ]

    PAYMENT_METHODS = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        # ... other methods
    ]

    TRANSACTION_STATUSES = [
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        # ... other statuses
    ]

    transaction_id = models.CharField(
        max_length=50, unique=True, db_index=True, verbose_name="Transaction ID")
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.SET_NULL, null=True,
        verbose_name="Customer")
    order = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.SET_NULL, null=True,
        verbose_name="Order")
    payment_gateway = models.CharField(
        max_length=20, blank=True, choices=PAYMENT_GATEWAYS,
        verbose_name="Payment Gateway")
    payment_method = models.CharField(
        max_length=20, blank=True, choices=PAYMENT_METHODS,
        verbose_name="Payment Method")
    transaction_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        verbose_name="Transaction Amount")
    currency = models.CharField(
        max_length=10, default='USD', verbose_name="Currency")
    transaction_status = models.CharField(
        max_length=20, default='processing', db_index=True, choices=TRANSACTION_STATUSES,
        verbose_name="Transaction Status")
    transaction_date = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="Transaction Date")
    payer_email = models.EmailField(blank=True, verbose_name="Payer Email")
    gateway_transaction_id = models.CharField(
        max_length=100, blank=True, verbose_name="Gateway Transaction ID")
    payment_response = models.JSONField(
        blank=True, null=True, default=dict, verbose_name="Payment Response")

    class Meta:
        db_table = "Payment"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"


# Transaction tables:

class OrderHasAddress(models.Model):
    address = models.ForeignKey(
        'General.Address', on_delete=models.CASCADE)
    order = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'order_has_address'


class OrderLineItem(models.Model):
    product = models.ForeignKey(
        'Product.ProductInstance', on_delete=models.CASCADE)
    order = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.CASCADE)
    quantity = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(99)], default=0)

    class Meta:
        db_table = 'order_line_item'


class CompleteSet(models.Model):
    order = models.ForeignKey(
        'Order.OrderInfo', on_delete=models.SET_NULL, null=True)
    frame = models.ForeignKey(
        'Product.ProductInstance', on_delete=models.CASCADE)
    usage = models.ForeignKey(
        'Lens.LensUsage', on_delete=models.SET_NULL, null=True)
    color = models.ForeignKey(
        'Lens.LensColor', on_delete=models.SET_NULL, null=True)
    coating = models.ForeignKey(
        'Lens.LensCoating', on_delete=models.SET_NULL, null=True)
    index = models.ForeignKey(
        'Lens.LensIndex', on_delete=models.SET_NULL, null=True)
    density = models.ForeignKey(
        'Lens.LensDensity', on_delete=models.SET_NULL, null=True)
    prescription = models.ManyToManyField(
        'Prescription.PrescriptionInfo', blank=True)
    saved_for_later = models.BooleanField(default=False)
    sub_total = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sub_color = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_sub_total(self):
        total_price = 0
        # Check if self.frame is not None
        if self.frame:
            # Check if self.frame.price is not None
            if self.frame.price is not None:
                total_price += self.frame.price
            else:
                # If self.frame.price is None, get the price from the linked ProductInfo
                # Ensure there's a link to a ProductInfo and it has a price
                if self.frame.product and self.frame.product.price is not None:
                    total_price += self.frame.product.price
        if self.usage:
            total_price += self.usage.price
        if self.color:
            total_price += self.color.price
        if self.coating:
            total_price += self.coating.price
        if self.index:
            total_price += self.index.price
        if self.density:
            total_price += self.density.price
        return total_price

    def save(self, *args, **kwargs):
        self.sub_total = self.calculate_sub_total()
        super(CompleteSet, self).save(*args, **kwargs)

    class Meta:
        db_table = 'CompleteSet'
        verbose_name = 'Complete Set'
        verbose_name_plural = 'Complete Sets'


class OrderCompletePrescription(models.Model):
    completeSet = models.ForeignKey(
        'Order.CompleteSet', on_delete=models.CASCADE)
    prescription = models.ForeignKey(
        'Prescription.PrescriptionInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'order_complete_prescription'
