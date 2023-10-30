from django.contrib import admin

from .models import Address, Coupon, ImageUpload

# Register your models here.


# class CouponAdmin(admin.ModelAdmin):
#     change_form_template = 'admin/custom_coupon_form.html'
class UploadImageAdmin(admin.ModelAdmin):
    list_display = ('title', 'image_url', 'created_at')

    def image_url(self, obj):
        if obj.image:
            return f'http://admin.eyelovewear.com/media/{obj.image.url}'
        return None


admin.site.register(Address)
admin.site.register(Coupon)
admin.site.register(ImageUpload, UploadImageAdmin)
