from django.db import models
from tinymce.models import HTMLField


class BlogInfo(models.Model):
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=150, default="Other")
    slug = models.SlugField(max_length=200, unique=True, null=True, blank=True)
    content = HTMLField()
    sub_title = models.CharField(max_length=200, blank=True, null=True)
    brief = models.TextField(blank=True, null=True)
    home_page_img = models.ImageField(
        upload_to='blog_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'BlogInfo'
        verbose_name = 'Blog'
        verbose_name_plural = 'Blogs'
