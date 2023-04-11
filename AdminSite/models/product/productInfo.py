from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class ProductInfo(models.Model):
    model_number = models.CharField(max_length=20)
    sku = models.CharField(unique=True, max_length=20)
    stock = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(null=True)
    # Multiple size?
    letter_size = models.CharField(choices=['XS', 'S', 'M', 'L', 'XL'])
    string_size = models.CharField(max_length=10)
    frame_weight = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(999)])
    bifocal = models.BooleanField(default=False)
    material = models.CharField(
        choices=[
            'Acetate',
            'Titanium',
            'Plastic',
            'Carbon Fiber',
            'Mixed',
            'Metal',
            'Aluminium Alloy',
            'Wood',
            'TR90',
            'Ultem',
            'Memory Titanium',
            'Stainless Steel'])
    shape = models.CharField(
        choices=[
            'Rectangle',
            'Round',
            'Square',
            'Oval',
            'Cat-Eye',
            'Aviator',
            'Horn',
            'Browline',
            'Geometric',
            'Heart',
            'Butterfly',
            'Irregular',
            'Other'])
    gender = models.CharField(
        choices=["Male", "Female", "Unisex"], default="Unisex")
    nose_pad = models.CharField(
        choices=['Standard', 'Asian Fit', 'Adjustable'])
    frame_style = models.CharField(
        choices=['Full-Rim', 'Semi-Rimless', 'Rimless'])
    pd_upper_range = models.IntegerField(default=80)
    pd_lower_range = models.IntegerField(default=30)
    color_name = models.CharField(max_length=50)
    online = models.CharField(default=False)
    reduced_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
