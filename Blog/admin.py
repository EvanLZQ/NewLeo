from django.contrib import admin
from .models import *

# Register your models here.
#admin.site.register(BlogInfo)
@admin.register(BlogInfo)
class BlogInfoAdmin(admin.ModelAdmin):
    pass
