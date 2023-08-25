from django.contrib import admin

from .models import Address, Coupon

# Register your models here.


# class CouponAdmin(admin.ModelAdmin):
#     change_form_template = 'admin/custom_coupon_form.html'


admin.site.register(Address)
admin.site.register(Coupon)
