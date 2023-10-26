from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe


class ProductImageInline(admin.StackedInline):
    model = ProductImage


class ProductInstanceInline(admin.StackedInline):
    inlines = [ProductImageInline, ]
    model = ProductInstance
    extra = 1
    readonly_fields = ('color_image_preview')

    # def carousel_image_preview(self, obj):
    #     images = obj.carousel_img.split(',') if obj.carousel_img else []
    #     html = ""
    #     for image in images:
    #         html += f'<img src="{image}" style="max-width: 300px; margin: 5px;">'
    #     return mark_safe(html)
    # carousel_image_preview.short_description = 'Carousel Images Preview'

    # def detail_image_preview(self, obj):
    #     images = obj.detail_img.split(',') if obj.detail_img else []
    #     html = ""
    #     for image in images:
    #         html += f'<img src="{image}" style="max-width: 300px; margin: 5px;">'
    #     return mark_safe(html)
    # detail_image_preview.short_description = 'Detail Images Preview'

    def color_image_preview(self, obj):
        return mark_safe(f'<img src="{obj.color_img_url}" style="max-width: 300px; margin: 5px; border-style: solid;">')
    color_image_preview.short_description = 'Color Image Preview'


class ProductInstanceAdmin(admin.ModelAdmin):

    @admin.display(description="Model Number")
    def get_model_number(self, obj):
        return obj.product.model_number

    list_display = ['get_model_number', 'sku', 'online']
    readonly_fields = ['color_image_preview',
                       'carousel_image_preview', 'detail_image_preview']


class ProductInfoAdmin(admin.ModelAdmin):
    inlines = [ProductInstanceInline,]

# class ImageInline(admin.TabularInline):
#     model = ProductImage
#     extra = 1
#     readonly_fields = ['display_image']

#     @admin.display(description="Image")
#     def display_image(self, obj):
#         return format_html('<img src="{}" width="300" />', obj.image_url)


# class ProductAdmin(admin.ModelAdmin):
#     prepopulated_fields = {'slug': ['sku']}

# list_display = [
#     'sku',
#     'get_first_image'
# ]

# @admin.display(description="Product Image")
# def get_first_image(self, obj):
#     try:
#         img = obj.productimage.first().image_url
#         return format_html('<img src="%s" width="300"  />' % (img))
#     except:
#         return None

# inlines = [
#     ImageInline,
# ]


# class ProductImageAdmin(admin.ModelAdmin):
#     fields = ['productID', 'slug', 'image_type',
#               'name', 'image_url', 'product_image', 'description']
#     readonly_fields = ['product_image']


admin.site.register(ProductInfo, ProductInfoAdmin)
admin.site.register(ProductPromotion)
# admin.site.register(ProductDimension)
# admin.site.register(ProductFeature)
# admin.site.register(ProductImage, ProductImageAdmin)
admin.site.register(ProductInstance, ProductInstanceAdmin)
admin.site.register(ProductReview)
admin.site.register(ProductTag)
