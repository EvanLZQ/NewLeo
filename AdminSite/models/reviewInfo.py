from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User

# Create your models here.


class ReviewInfo(models.Model):
    ReviewID = models.AutoField(primary_key=True)
    title = models.CharField(max_length=100)
    content = models.TextField()
    user_email = models.EmailField()
    online = models.BooleanField(default=False)
    sku = models.CharField(max_length=100)
    rating = models.IntegerField(
        default=5,
        validators=[
            MaxValueValidator(5),
            MinValueValidator(1)
        ])
    approved_by = models.ManyToManyField(User)
