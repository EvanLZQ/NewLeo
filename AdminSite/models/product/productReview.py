from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

# from .productInfo import ProductInfo


class ProductReview(models.Model):
    ProductID = models.ForeignKey(
        'AdminSite.ProductInfo', on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    content = models.TextField(blank=True)
    user_email = models.EmailField()
    online = models.BooleanField(default=False)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ManyToManyField(User, blank=True)
