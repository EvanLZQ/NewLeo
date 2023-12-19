from django.contrib import admin

from .models import CustomerInfo, ShoppingCart, WishList, CustomerMessage, CustomerNotification

# Register your models here.


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'full_name', 'phone')


class CustomerMessageAdmin(admin.ModelAdmin):
    list_display = ('customer', 'subject', 'sent_at',
                    'read_at', 'message_from')


class CustomerNotificationAdmin(admin.ModelAdmin):
    list_display = ('customer', 'title', 'created_at')


admin.site.register(CustomerInfo, CustomerAdmin)
admin.site.register(ShoppingCart)
admin.site.register(WishList)
admin.site.register(CustomerNotification, CustomerNotificationAdmin)
admin.site.register(CustomerMessage, CustomerMessageAdmin)
