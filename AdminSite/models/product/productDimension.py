from django.db import models
# from .productInfo import ProductInfo


class ProductDimension(models.Model):
    productID = models.ForeignKey(
        'AdminSite.ProductInfo', on_delete=models.CASCADE, related_name='product_dimension')
    frame_width = models.IntegerField()
    lens_width = models.IntegerField()
    bridge = models.IntegerField()
    temple_length = models.IntegerField()
    lens_height = models.IntegerField()
    upper_wearable_width = models.IntegerField()
    lower_wearable_width = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
