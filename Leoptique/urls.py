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
from django.urls import path, include
# from rest_framework.authtoken.views import obtain_auth_token
from .views import CookieTokenObtainPairView, CookieTokenRefreshView
from .serializer import CookieTokenRefreshSerializer
# from rest_framework_simplejwt.views import (
#     TokenObtainPairView,
#     TokenRefreshView,
# )


admin.site.site_header = 'Leoptique Admin Site'
admin.site.site_title = 'Leoptique Admin'
admin.site.index_title = 'Home Page'

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/products/", include("Product.urls")),
    path("api/lens/", include("Lens.urls")),
    # path('api/token/', obtain_auth_token, name='obtain-token'),
    path('api/token/', CookieTokenObtainPairView.as_view(),
         name='token_obtain_pair'),
    path('api/token/refresh/', CookieTokenRefreshView.as_view(),
         name='token_refresh'),
    path('api/user/', include("Customer.urls")),
    path('api/order/', include("Order.urls"))
]
