from django.db import models

from .productInfo import ProductInfo


class ProductFeature(models.Model):
    product = models.ManyToManyField(ProductInfo)
    name = models.CharField(max_length=20)
    description = models.TextField()
    image = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
