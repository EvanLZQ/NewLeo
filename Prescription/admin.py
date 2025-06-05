from django.contrib import admin

from .models import *
# Register your models here.


@admin.register(PrescriptionInfo)
class PrescriptionInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nickname', 'created_at')


@admin.register(PrescriptionPrism)
class PrescriptionPrismAdmin(admin.ModelAdmin):
    list_display = ('id', 'prescription',
                    'horizontal_value_r', 'vertical_value_r')
