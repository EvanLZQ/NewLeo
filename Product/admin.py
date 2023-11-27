from django import forms
from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe


class ProductTagInline(admin.TabularInline):
    model = ProductTag.product.through


class ProductImageInline(admin.StackedInline):
    model = ProductImage
    extra = 1
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        return mark_safe(f'<img src="https://admin.eyelovewear.com/media/{obj.image}" style="max-width: 300px; margin: 5px;">')
    image_preview.short_description = 'To see the image, click Save and Continue Editing.'


class ProductInstanceInline(admin.StackedInline):
    model = ProductInstance
    extra = 1


class ProductInstanceAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ]

    @admin.display(description="Model Number")
    def get_model_number(self, obj):
        return obj.product.model_number

    list_display = ['get_model_number', 'sku', 'online']
    # readonly_fields = ['color_image_preview']


class ProductInfoAdmin(admin.ModelAdmin):
    inlines = [ProductInstanceInline, ProductTagInline]

    def get_inline_instances(self, request, obj=None):
        inline_instances = super().get_inline_instances(request, obj)
        for inline_instance in inline_instances:
            if isinstance(inline_instance, ProductTagInline):
                inline_instance.verbose_name = "Product Tag"
                inline_instance.verbose_name_plural = "Product Tags"
        return inline_instances


class ProductColorImgAdmin(admin.ModelAdmin):
    readonly_fields = ['color_image_preview']

    def color_image_preview(self, obj):
        return mark_safe(f'<img src="https://admin.eyelovewear.com{obj.color_img.url}" style="max-width: 300px; margin: 5px; border-style: solid;">')

    color_image_preview.short_description = 'Color Image Preview'


admin.site.register(ProductInfo, ProductInfoAdmin)
admin.site.register(ProductPromotion)
admin.site.register(ProductInstance, ProductInstanceAdmin)
admin.site.register(ProductReview)
admin.site.register(ProductTag)
admin.site.register(ProductColorImg, ProductColorImgAdmin)
