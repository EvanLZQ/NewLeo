from django.urls import path
from . import views

urlpatterns = [
    path('currency', views.getCurrencyConversion, name='currency'),
    path('faq', views.getFAQContents, name='faq'),
]
