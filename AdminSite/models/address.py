from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

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

