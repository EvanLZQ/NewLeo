from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe
# Register your models here.


class BlogInfoAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    ordering = ('-created_at',)
    change_form_template = "admin/Blog/change_form.html"


admin.site.register(BlogInfo, BlogInfoAdmin)
