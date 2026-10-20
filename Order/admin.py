from django.contrib import admin

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


@admin.register(OrderInfo)
class OrderInfoAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'email', 'order_status', 'payment_status',
                    'total_amount', 'shipping_company', 'tracking_number',
                    'created_at')
    list_filter = ('order_status', 'payment_status', 'payment_type')
    search_fields = ('order_number', 'email', 'tracking_number')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = [OrderStatusEventInline]


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
admin.site.register(CompleteSet)
