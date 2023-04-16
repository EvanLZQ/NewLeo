from django.contrib import admin
from .models import CustomerInfo

# Register your models here.


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'phone')


admin.register(CustomerInfo, CustomerAdmin)
