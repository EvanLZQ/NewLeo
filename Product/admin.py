from django import forms
from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe


class ProductInfoForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=ProductTag.objects.all(),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('tags', False)
    )

    class Meta:
        model = ProductInfo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['tags'].initial = self.instance.producttag_set.all()

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        if instance.pk:
            instance.producttag_set.set(self.cleaned_data['tags'])
            self.save_m2m()
        return instance


class ProductImageInline(admin.StackedInline):
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        return mark_safe(f'<img src="http://admin.eyelovewear.com/media/{obj.image_url}.webp" style="max-width: 300px; margin: 5px;">')
    image_preview.short_description = 'To see the image, click Save and Continue Editing.'

    model = ProductImage


class ProductInstanceInline(admin.StackedInline):
    model = ProductInstance
    extra = 1
    readonly_fields = ['color_image_preview']

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
    inlines = [ProductImageInline, ]

    @admin.display(description="Model Number")
    def get_model_number(self, obj):
        return obj.product.model_number

    list_display = ['get_model_number', 'sku', 'online']
    readonly_fields = ['color_image_preview']


class ProductInfoAdmin(admin.ModelAdmin):
    inlines = [ProductInstanceInline,]
    form = ProductInfoForm

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
