from django.contrib import admin

from .models import CustomerInfo, ShoppingCart, WishList

# Register your models here.


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'full_name', 'phone')


admin.site.register(CustomerInfo, CustomerAdmin)
admin.site.register(ShoppingCart)
admin.site.register(WishList)
