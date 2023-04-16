from django.contrib import admin
# from .models import ReviewInfo
from .models import CustomerInfo

# Register your models here.


# class ReviewAdmin(admin.ModelAdmin):
#     list_display = ("title", "user_email",
#                     "sku", "online")


# admin.site.register(ReviewInfo, ReviewAdmin)
admin.site.register(CustomerInfo)
