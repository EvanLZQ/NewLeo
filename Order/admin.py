from django.contrib import admin

from .models import *
# Register your models here.

admin.site.register(OrderInfo)
admin.site.register(OrderImage)
admin.site.register(OrderTax)
admin.site.register(OrderUpdates)
admin.site.register(CompleteSet)
