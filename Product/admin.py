from django import forms
from django.contrib import admin
from .models import *
from django.utils.safestring import mark_safe


class ProductImportForm(forms.Form):  # 使用 Form（不落库）
    excel_file = forms.FileField(  # Excel 上传字段
        label="Excel 文件（.xlsx）",  # 字段显示名
        help_text="必须包含 sheet：Product、ProductImage，且列名固定。",  # 说明
    )  # 字段结束
    images_zip_file = forms.FileField(  # zip 上传字段
        label="图片 zip 文件（.zip）",  # 字段显示名
        help_text="zip 内文件路径/文件名应与 ProductImage.images 列匹配（支持容错）。",  # 说明
    )  # 字段结束
    replace_existing_images = forms.BooleanField(  # 是否替换旧图片
        label="替换已有图片（删除旧 ProductImage 记录）",  # 显示名
        required=False,  # 可选
        initial=False,  # 默认不替换（更安全）
    )  # 字段结束

    def clean_excel_file(self):  # 校验 Excel 扩展名
        f = self.cleaned_data["excel_file"]  # 取文件
        if not f.name.lower().endswith(".xlsx"):  # 只允许 xlsx
            raise forms.ValidationError("请上传 .xlsx 格式的 Excel")  # 抛表单错误
        return f  # 返回文件

    def clean_images_zip_file(self):  # 校验 zip 扩展名
        f = self.cleaned_data["images_zip_file"]  # 取文件
        if not f.name.lower().endswith(".zip"):  # 只允许 zip
            raise forms.ValidationError("请上传 .zip 格式的图片压缩包")  # 抛表单错误
        return f  # 返回文件


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
