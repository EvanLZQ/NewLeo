from django.contrib import admin

from .models import Address, Coupon, ImageUpload, CurrencyConversion, FAQ, PageImage

# Register your models here.


# class CouponAdmin(admin.ModelAdmin):
#     change_form_template = 'admin/custom_coupon_form.html'
class UploadImageAdmin(admin.ModelAdmin):
    list_display = ('title', 'image_url', 'created_at')

    def image_url(self, obj):
        if obj.image:
            return f'https://admin.eyelovewear.com{obj.image.url}'
        return None


admin.site.register(Address)
admin.site.register(Coupon)
admin.site.register(ImageUpload, UploadImageAdmin)
admin.site.register(CurrencyConversion)
admin.site.register(FAQ)
admin.site.register(PageImage)
