from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.getProducts, name='products'),
    path('products/<str:sku>/', views.getProduct, name='product_details'),
]
