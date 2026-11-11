from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import *
from .models import OrderStatusEvent  # not in models.__all__
# Register your models here.


class OrderStatusEventInline(admin.TabularInline):
    """Read-only trail of status changes (written by Order/signals.py)."""
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    readonly_fields = ('status', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


def _upload_link(upload):
    if upload is None or not upload.file:
        return "-"
    return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>',
                       reverse('prescription-upload-file', args=[upload.pk]),
                       upload.original_name or "Prescription file")


@admin.register(CompleteSet)
class CompleteSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'frame', 'lens_type', 'order', 'prescription',
                    'prescription_file', 'sub_total', 'created_at')
    list_select_related = ('frame', 'lens_type', 'order', 'prescription', 'prescription_upload')
    raw_id_fields = ('prescription_upload',)
    readonly_fields = ('prescription_file', 'created_by')

    @admin.display(description='Rx upload')
    def prescription_file(self, obj):
        return _upload_link(obj.prescription_upload)


class CompleteSetInline(admin.TabularInline):
    """Pairs on this order, with the uploaded prescription file if any."""
    model = CompleteSet
    extra = 0
    can_delete = False
    fields = ('id', 'frame', 'lens_type', 'prescription', 'prescription_file', 'sub_total')
    readonly_fields = fields
    show_change_link = True

    @admin.display(description='Rx upload')
    def prescription_file(self, obj):
        return _upload_link(obj.prescription_upload)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrderInfo)
class OrderInfoAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'email', 'order_status', 'payment_status',
                    'total_amount', 'shipping_company', 'tracking_number',
                    'created_at')
    list_filter = ('order_status', 'payment_status', 'payment_type')
    search_fields = ('order_number', 'email', 'tracking_number')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = [CompleteSetInline, OrderStatusEventInline]


@admin.register(OrderPayment)
class OrderPaymentAdmin(admin.ModelAdmin):
    """Payment ledger. Everything here comes from the gateway's own response,
    so it is view-only: editing it would only make the books disagree with
    PayPal."""
    list_display = ('transaction_id', 'order', 'payment_gateway',
                    'transaction_amount', 'currency', 'transaction_status',
                    'payer_email', 'transaction_date')
    list_filter = ('payment_gateway', 'transaction_status')
    search_fields = ('transaction_id', 'gateway_transaction_id',
                     'payer_email', 'order__order_number')
    date_hierarchy = 'transaction_date'
    ordering = ('-transaction_date',)
    raw_id_fields = ('order', 'customer')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(OrderImage)
admin.site.register(OrderUpdates)

