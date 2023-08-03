from django.urls import path
from . import views

urlpatterns = [
    path('', views.getProducts, name='products'),
    path('sku<str:sku>/', views.getProduct, name='product_details'),
    path('<str:model>/', views.getModel, name='model_details'),
    path('filter', views.filterProduct, name='filter_products'),
]
