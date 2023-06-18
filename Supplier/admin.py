from django.contrib import admin
from .models import SupplierInfo

# Register your models here.


class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'website', 'phone', 'email']


admin.site.register(SupplierInfo, SupplierAdmin)
