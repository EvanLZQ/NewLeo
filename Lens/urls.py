from django.urls import path
from . import views

urlpatterns = [
    path('usage', views.getLensUsage, name='lens_usage'),
    path('color', views.getLensColor, name='lens_color'),
    path('density', views.getLensDensity, name='lens_density'),
    path('coating', views.getLensCoating, name='lens_coating'),
    path('index', views.getLensIndex, name='lens_index'),
]
