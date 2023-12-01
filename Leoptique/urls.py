"""Leoptique URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from . import views


admin.site.site_header = 'Leoptique Admin Site'
admin.site.site_title = 'Leoptique Admin'
admin.site.index_title = 'Home Page'

urlpatterns = [
    path("admin/", admin.site.urls),
    # path("admin/Blog/bloginfo/add/tinymce/upload_image",
    #      views.upload_image, name="tinymce_upload"),
    path("api/products/", include("Product.urls")),
    path("api/lens/", include("Lens.urls")),
    path('api/user/', include("Customer.urls")),
    path('api/order/', include("Order.urls")),
    path('api/blog/', include("Blog.urls")),
    path('api/general/', include("General.urls")),
    re_path(r'^auth/', include('drf_social_oauth2.urls', namespace='drf')),
]
