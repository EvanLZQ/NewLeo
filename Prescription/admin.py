from django.contrib import admin
from django.utils.html import format_html

from .models import *
# Register your models here.


@admin.register(PrescriptionInfo)
class PrescriptionInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nickname', 'created_at')


@admin.register(PrescriptionPrism)
class PrescriptionPrismAdmin(admin.ModelAdmin):
    list_display = ('id', 'prescription',
                    'horizontal_value_r', 'vertical_value_r')


@admin.register(PrescriptionUpload)
class PrescriptionUploadAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'content_type', 'size_kb', 'customer',
                    'complete_sets_list', 'created_at', 'file_link')
    list_filter = ('content_type', 'created_at')
    search_fields = ('original_name', 'customer__email', 'id')
    readonly_fields = ('id', 'customer', 'original_name', 'content_type', 'size',
                       'created_at', 'file_link', 'preview')
    fields = readonly_fields + ('file',)

    @admin.display(description='Size')
    def size_kb(self, obj):
        return f"{obj.size / 1024:.0f} KB"

    @admin.display(description='Cart items / orders')
    def complete_sets_list(self, obj):
        sets = list(obj.complete_sets.all()[:5])
        return ", ".join(
            f"#{s.id}" + (f" (order {s.order.order_number})" if s.order_id else "")
            for s in sets) or "-"

    @admin.display(description='File')
    def file_link(self, obj):
        if not obj.file:
            return "-"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open</a>', obj.file.url)

    @admin.display(description='Preview')
    def preview(self, obj):
        if not obj.file or obj.is_pdf:
            return self.file_link(obj)
        return format_html('<a href="{0}" target="_blank" rel="noopener">'
                           '<img src="{0}" style="max-width:420px;max-height:420px"></a>',
                           obj.file.url)
