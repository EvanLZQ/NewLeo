from django.contrib import admin

from .models import CustomerInfo, ShoppingList, WishList

# Register your models here.


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'full_name', 'phone')


admin.site.register(CustomerInfo, CustomerAdmin)
admin.site.register(ShoppingList)
admin.site.register(WishList)
