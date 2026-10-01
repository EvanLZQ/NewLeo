from django.contrib import admin

from .models import Address, Coupon, ImageUpload, CurrencyConversion, FAQ, PageImage, NewsletterSubscriber

# Register your models here.


# class CouponAdmin(admin.ModelAdmin):
#     change_form_template = 'admin/custom_coupon_form.html'
class UploadImageAdmin(admin.ModelAdmin):
    list_display = ('title', 'image_url', 'created_at')

    def image_url(self, obj):
        if obj.image:
            return f'https://admin.eyelovewear.com{obj.image.url}'
        return None


class PageImageAdmin(admin.ModelAdmin):
    list_display = ('page', 'section', 'order')


class FAQAdmin(admin.ModelAdmin):
    list_display = ('title', 'sort_order', 'updated_at')
    # Edit the sort number right from the list page instead of opening
    # each row — reordering FAQs is a frequent, low-stakes edit.
    list_editable = ('sort_order',)
    ordering = ('sort_order', 'id')
    search_fields = ('title', 'content')


admin.site.register(Address)
admin.site.register(Coupon)
admin.site.register(ImageUpload, UploadImageAdmin)
admin.site.register(CurrencyConversion)
admin.site.register(FAQ, FAQAdmin)
admin.site.register(PageImage, PageImageAdmin)


class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'subscribed_at', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('email',)
    ordering = ('-subscribed_at',)


admin.site.register(NewsletterSubscriber, NewsletterSubscriberAdmin)
