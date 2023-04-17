from django.contrib import admin

from .models import *

# Register your models here.

admin.site.register(ProductInfo)
admin.site.register(ProductDimension)
admin.site.register(ProductFeature)
admin.site.register(ProductImage)
admin.site.register(ProductReview)
admin.site.register(ProductTag)
