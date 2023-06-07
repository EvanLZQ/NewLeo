from django.contrib import admin
from django.utils.html import format_html


from .models import *

# Register your models here.


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    readonly_fields = ['display_image']

    @admin.display(description="Image")
    def display_image(self, obj):
        return format_html('<img src="{}" width="300" />', obj.image_url)


class ProductAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ['sku']}

    list_display = [
        'sku',
        'get_first_image'
    ]

    @admin.display(description="Product Image")
    def get_first_image(self, obj):
        try:
            img = obj.productimage.first().image_url
            return format_html('<img src="%s" width="300"  />' % (img))
        except:
            return None

    inlines = [
        ImageInline,
    ]


class ProductImageAdmin(admin.ModelAdmin):
    fields = ['productID', 'colorID', 'slug', 'image_type',
              'name', 'image_url', 'product_image', 'description']
    readonly_fields = ['product_image']


admin.site.register(ProductInfo, ProductAdmin)
admin.site.register(ProductCollection)
admin.site.register(ProductDimension)
admin.site.register(ProductFeature)
admin.site.register(ProductImage, ProductImageAdmin)
admin.site.register(ProductReview)
admin.site.register(ProductTag)
