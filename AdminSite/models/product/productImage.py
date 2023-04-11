from django.db import models
from .productInfo import ProductInfo


class ProductImage(models.Model):
    productID = models.ForeignKey(ProductInfo, on_delete=models.CASCADE)
    image_type = models.CharField(max_length=50)
    name = models.CharField(max_length=20)
    path = models.URLField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
