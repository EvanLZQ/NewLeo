from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.


class Address(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.CASCADE, related_name='addresses', null=True, blank=True)
    full_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=50)
    province_state = models.CharField(max_length=50)
    country = models.CharField(max_length=50)
    post_code = models.CharField(max_length=10)
    instruction = models.TextField(blank=True, null=True)
    default_address = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Check if this is the only address for the customer
            if Address.objects.filter(customer=self.customer).count() == 0:
                # This is the only address, so set it as default
                self.default_address = True
            elif self.default_address:
                # If this is not the only address but is being set as default,
                # unset the default for other addresses
                Address.objects.filter(customer=self.customer, default_address=True).exclude(
                    id=self.id).update(default_address=False)

        super(Address, self).save(*args, **kwargs)

    class Meta:
        db_table = 'Address'
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'


class Coupon(models.Model):
    DISCOUNT_TYPE = [
        ("Percentage", "Percentage"), ("Amount", "Amount")
    ]
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(max_length=1000, null=True, blank=True)
    img_url = models.URLField(max_length=200, blank=True, null=True)
    expire_date = models.DateField(null=True, blank=True)
    online = models.BooleanField(default=False)
    # applied product list
    applied_product = models.ManyToManyField(
        "Product.ProductInstance", related_name='coupons')
    # valid customer list
    valid_customer = models.ManyToManyField(
        "Customer.CustomerInfo", related_name='coupons')
    # discount type for frame
    frame_discount_type = models.CharField(
        max_length=50, choices=DISCOUNT_TYPE, default="Percentage")
    # discount amount for frame
    frame_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    # discount type for lens
    lens_discount_type = models.CharField(
        max_length=50, choices=DISCOUNT_TYPE, default="Percentage")
    # discount amount for lens
    lens_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    # discount type for shipping
    shipping_discount_type = models.CharField(
        max_length=50, choices=DISCOUNT_TYPE, default="Percentage")
    # discount amount for shipping
    shipping_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    # discount type for order
    order_discount_type = models.CharField(
        max_length=50, choices=DISCOUNT_TYPE, default="Percentage")
    # discount amount for order
    order_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

    class Meta:
        db_table = 'Coupon'
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'


class ImageUpload(models.Model):
    title = models.CharField(max_length=150)
    image = models.ImageField(upload_to='uploaded_images/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ImageUpload'
        verbose_name = 'Image Upload'
        verbose_name_plural = 'Image Uploads'


class CurrencyConversion(models.Model):
    currency = models.CharField(max_length=50)
    symbol = models.CharField(max_length=50)
    rate = models.DecimalField(max_digits=10, decimal_places=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'CurrencyConversion'
        verbose_name = 'Currency Conversion'
        verbose_name_plural = 'Currency Conversions'
