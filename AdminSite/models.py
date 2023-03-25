from django.db import models

# Create your models here.


class ReviewInfo(models.Model):
    ReviewID = models.AutoField(primary_key=True)
    ReviewTitle = models.CharField(max_length=100)
    ReviewContent = models.TextField()
