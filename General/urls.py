from django.urls import path
from . import views

urlpatterns = [
    path('currency', views.getCurrencyConversion, name='currency'),
]
