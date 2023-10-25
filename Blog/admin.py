from django.contrib import admin
from .models import *

# Register your models here.


class BlogInfoAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    ordering = ('-created_at',)


admin.site.register(BlogInfo, BlogInfoAdmin)


# @admin.register(BlogInfo)
# class BlogInfoAdmin(admin.ModelAdmin):
#     pass
