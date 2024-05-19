from django.urls import path
from . import views

urlpatterns = [
    path('currency', views.getCurrencyConversion, name='currency'),
    path('faq', views.getFAQContents, name='faq'),
    path('page_image', views.getPageImage, name='page_image')
]
