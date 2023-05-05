from django.db import models

# Create your models here.


class ColorInfo(models.Model):
    display_name = models.CharField(max_length=100)
    base_name = models.CharField(max_length=200)
    image_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = 'Color'
        verbose_name_plural = 'Colors'
