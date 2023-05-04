from django.contrib import admin

from .models import *

# Register your models here.


class ProductAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ['sku']}

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('slug',)
        return self.readonly_fields


admin.site.register(ProductInfo, ProductAdmin)
admin.site.register(ProductDimension)
admin.site.register(ProductFeature)
admin.site.register(ProductImage)
admin.site.register(ProductReview)
admin.site.register(ProductTag)
