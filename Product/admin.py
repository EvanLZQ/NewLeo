from django import forms  # Admin 上传表单
from django.contrib import admin, messages  # admin + 消息提示
from django.core.exceptions import ValidationError  # 捕获 importer 的可读错误
from django.http import HttpRequest, HttpResponse  # 类型注解
from django.template.response import TemplateResponse  # 渲染模板
from django.urls import path  # 给 ModelAdmin 加自定义 url
from django.shortcuts import redirect  # 通用重定向
from django.utils.safestring import mark_safe  # 预览图片 HTML

from .models import *
from Product.services.product_importer import import_products_from_excel_and_zip


class ProductImportForm(forms.Form):  # 不落库的上传表单
    excel_file = forms.FileField(label="Excel 文件（.xlsx）")  # Excel 上传
    images_zip_file = forms.FileField(label="图片 zip 文件（.zip）")  # zip 上传
    replace_existing_images = forms.BooleanField(  # 是否替换旧图
        label="替换已有图片（删除旧 ProductImage 记录）",
        required=False,
        initial=False,
    )

    def clean_excel_file(self):  # 校验 Excel 格式
        f = self.cleaned_data["excel_file"]  # 取文件对象
        if not f.name.lower().endswith(".xlsx"):  # 只允许 .xlsx
            raise forms.ValidationError("请上传 .xlsx 格式的 Excel")  # 表单错误
        return f  # 返回

    def clean_images_zip_file(self):  # 校验 zip 格式
        f = self.cleaned_data["images_zip_file"]  # 取文件对象
        if not f.name.lower().endswith(".zip"):  # 只允许 .zip
            raise forms.ValidationError("请上传 .zip 格式的图片压缩包")  # 表单错误
        return f  # 返回


class ProductTagInline(admin.TabularInline):
    model = ProductTag.product.through  # M2M through 表


class ProductImageInline(admin.StackedInline):
    model = ProductImage  # 图片模型
    extra = 1  # 默认多一行
    readonly_fields = ["image_preview"]  # 只读预览

    def image_preview(self, obj):  # 预览函数
        if not obj or not obj.image:  # 没有图片就显示占位
            return "-"  # 占位
        # 用 obj.image.url 更稳
        return mark_safe(f'<img src="{obj.image.url}" style="max-width: 300px; margin: 5px;">')

    image_preview.short_description = "Preview"  # 列名


class ProductInstanceInline(admin.StackedInline):
    model = ProductInstance
    extra = 1


class ProductInstanceAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ]

    @admin.display(description="Model Number")
    def get_model_number(self, obj):
        return obj.product.model_number if obj.product else "-"

    list_display = ["get_model_number", "sku", "online"]


class ProductInfoAdmin(admin.ModelAdmin):
    inlines = [ProductInstanceInline, ProductTagInline]  # 保留你原有 inline

    change_list_template = "product_import/productinfo_change_list.html"  # 关键：指向你当前模板真实路径

    def get_inline_instances(self, request, obj=None):  # 你原来的逻辑：改 verbose_name
        inline_instances = super().get_inline_instances(request, obj)  # 获取 inline
        for inline_instance in inline_instances:  # 遍历 inline
            if isinstance(inline_instance, ProductTagInline):  # 找到 ProductTagInline
                inline_instance.verbose_name = "Product Tag"  # 单数
                inline_instance.verbose_name_plural = "Product Tags"  # 复数
        return inline_instances  # 返回

    def get_urls(self):  # 关键：注册 /import/ 路由
        urls = super().get_urls()  # 取原 urls
        custom_urls = [  # 自定义 urls
            path(  # 路由定义
                "import/",  # 访问路径：.../productinfo/import/
                self.admin_site.admin_view(self.import_view),  # 权限保护
                # url name
                name=f"{self.model._meta.app_label}_{self.model._meta.model_name}_import",
            )
        ]
        return custom_urls + urls  # 放前面优先匹配

    def import_view(self, request: HttpRequest) -> HttpResponse:  # 导入页面处理函数
        if request.method == "POST":  # 提交表单
            form = ProductImportForm(request.POST, request.FILES)  # 绑定请求数据
            if form.is_valid():  # 校验通过
                try:
                    excel_f = form.cleaned_data["excel_file"]  # 取 Excel
                    zip_f = form.cleaned_data["images_zip_file"]  # 取 zip

                    # 防止保存到别处后文件指针不在开头（稳一点）
                    try:
                        excel_f.seek(0)  # 回到文件头
                    except Exception:
                        pass  # 不支持 seek 就忽略

                    try:
                        zip_f.seek(0)  # 回到文件头
                    except Exception:
                        pass  # 不支持 seek 就忽略

                    result = import_products_from_excel_and_zip(  # 调用 importer
                        excel_file=excel_f,  # Excel
                        images_zip_file=zip_f,  # zip
                        # 参数
                        replace_existing_images=form.cleaned_data["replace_existing_images"],
                    )

                    messages.success(  # 成功提示
                        request,
                        (
                            f"导入完成：ProductInfo 新建 {result.productinfo_created} / 更新 {result.productinfo_updated}；"
                            f"ProductInstance 新建 {result.instance_created} / 更新 {result.instance_updated}；"
                            f"ProductImage 新建 {result.images_created}。"
                        ),
                    )

                    if result.missing_tags:  # 缺失 tag 提示（最多显示 30 个）
                        messages.warning(
                            request, f"以下 ProductTag 未找到（已跳过绑定）：{', '.join(result.missing_tags[:30])}")

                    if result.missing_images:  # 缺失图片提示（最多显示 30 个）
                        messages.warning(
                            request, f"以下图片在 zip 内未找到（已跳过）：{', '.join(result.missing_images[:30])}")

                    return redirect("..")  # 回到 ProductInfo 列表页

                except ValidationError as e:  # importer 抛出的可读错误
                    messages.error(request, f"导入失败：{e}")  # 展示错误
                except Exception as e:  # 兜底异常
                    messages.error(request, f"导入失败（未知错误）：{e}")  # 展示错误
            else:
                messages.error(request, "表单校验失败，请检查文件类型与必填项")  # 表单失败提示
        else:
            form = ProductImportForm()  # GET：空表单

        context = {  # 模板上下文
            **self.admin_site.each_context(request),  # admin 基础上下文
            "opts": self.model._meta,  # 模型 meta
            "form": form,  # 表单
            "title": "导入产品（Excel + 图片 zip）",  # 标题
        }
        # 渲染你当前模板路径
        return TemplateResponse(request, "product_import/import_products.html", context)


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
