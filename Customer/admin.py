from django.contrib import admin

from .models import CustomerInfo, ShoppingList

# Register your models here.


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'phone')


admin.site.register(CustomerInfo, CustomerAdmin)
