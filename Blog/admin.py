from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe
# Register your models here.


class BlogInfoAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('home_page_img_preview',)

    def home_page_img_preview(self, obj):
        return mark_safe(f'<img src="http://admin.eyelovewear.com/{obj.home_page_img}" style="max-width: 300px; margin: 5px;">')
    home_page_img_preview.short_description = 'Home Page Image Preview'


admin.site.register(BlogInfo, BlogInfoAdmin)


# @admin.register(BlogInfo)
# class BlogInfoAdmin(admin.ModelAdmin):
#     pass
