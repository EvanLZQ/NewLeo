from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

# Create your models here.


class Address(models.Model):
    full_name = models.CharField(max_length=50)
    phone = PhoneNumberField()
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=50)
    province_state = models.CharField(max_length=50)
    country = models.CharField(max_length=50)
    post_code = models.CharField(max_length=10)
    instruction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Address'
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'
