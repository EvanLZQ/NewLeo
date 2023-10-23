from django.db import models


class BlogInfo(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=200, unique=True, null=True, blank=True)
    sub_title = models.CharField(max_length=200, blank=True, null=True)
    brief = models.TextField(blank=True, null=True)
    paragraph1 = models.TextField()
    paragraph2 = models.TextField(blank=True, null=True)
    paragraph3 = models.TextField(blank=True, null=True)
    paragraph4 = models.TextField(blank=True, null=True)
    paragraph5 = models.TextField(blank=True, null=True)
    paragraph6 = models.TextField(blank=True, null=True)
    paragraph7 = models.TextField(blank=True, null=True)
    paragraph8 = models.TextField(blank=True, null=True)
    paragraph9 = models.TextField(blank=True, null=True)
    paragraph10 = models.TextField(blank=True, null=True)
    paragraph11 = models.TextField(blank=True, null=True)
    paragraph12 = models.TextField(blank=True, null=True)
    paragraph13 = models.TextField(blank=True, null=True)
    paragraph14 = models.TextField(blank=True, null=True)
    paragraph15 = models.TextField(blank=True, null=True)
    paragraph16 = models.TextField(blank=True, null=True)
    paragraph17 = models.TextField(blank=True, null=True)
    paragraph18 = models.TextField(blank=True, null=True)
    paragraph19 = models.TextField(blank=True, null=True)
    paragraph20 = models.TextField(blank=True, null=True)
    paragraph21 = models.TextField(blank=True, null=True)
    paragraph22 = models.TextField(blank=True, null=True)
    paragraph23 = models.TextField(blank=True, null=True)
    top_img = models.CharField(max_length=1000, blank=True, null=True)
    left_top_img = models.CharField(max_length=1000, blank=True, null=True)
    right_top_img = models.CharField(max_length=1000, blank=True, null=True)
    center_img = models.CharField(max_length=1000, blank=True, null=True)
    left_bot_img = models.CharField(max_length=1000, blank=True, null=True)
    right_bot_img = models.CharField(max_length=1000, blank=True, null=True)
    bot_img = models.CharField(max_length=1000, blank=True, null=True)
    home_page_img = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'BlogInfo'
        verbose_name = 'Blog'
        verbose_name_plural = 'Blogs'
