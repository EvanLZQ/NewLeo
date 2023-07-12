from django.urls import path
from . import views

urlpatterns = [
    path('', views.getProducts, name='products'),
    path('<str:sku>/', views.getProduct, name='product_details'),
]
