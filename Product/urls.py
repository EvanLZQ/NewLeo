from django.urls import path
from . import views

urlpatterns = [
    path('', views.getProducts, name='products'),
    path('sku<str:sku>/', views.getProduct, name='product_details'),
    path('<str:model>/', views.getModel, name='model_details'),
    path('filter', views.filterProduct, name='filter_products'),
    path('skumodel/<str:sku>/', views.getModelUsingSku, name='model_by_sku'),
    path('paged_product', views.getPageProducts, name='page_products'),
    path('promotion', views.getProductPromotions, name='product_promotion'),
    path('getColorList', views.getAllColorNames, name='get_color_list'),
    path('getShapeList', views.getAllShapes, name='get_shape_list'),
    path('getMaterialList', views.getAllMaterials, name='get_material_list'),
    path('getSearchProduct', views.getSearchProducts, name='get_search_products'),
]
