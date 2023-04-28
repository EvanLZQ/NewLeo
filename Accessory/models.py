from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.


class AccessoryInfo(models.Model):
    slug = models.SlugField(unique=True, max_length=200)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=200, blank=True)
    order = models.ManyToManyField(
        'Order.OrderInfo', blank=True, through='OrderLineAccessory')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'AccessoryInfo'
        verbose_name = 'Accessory'
        verbose_name_plural = 'Accessories'


class AccessoryImage(models.Model):
    accessoryID = models.ForeignKey('AccessoryInfo', on_delete=models.CASCADE)
    image_type = models.CharField(max_length=200, blank=True)
    name = models.CharField(max_length=100)
    path = models.URLField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'AccessoryImage'
        verbose_name = 'Accessory Image'
        verbose_name_plural = 'Accessory Images'


class OrderLineAccessory(models.Model):
    orderID = models.ForeignKey('Order.OrderInfo', on_delete=models.CASCADE)
    accessoryID = models.ForeignKey('AccessoryInfo', on_delete=models.CASCADE)
    quantity = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=1)

    class Meta:
        db_table = 'order_line_accessory'
