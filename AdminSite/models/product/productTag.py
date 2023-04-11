from django.db import models
# from .productInfo import ProductInfo


class ProductTag(models.Model):
    product = models.ManyToManyField('AdminSite.ProductInfo')
    name = models.CharField(max_length=20)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
