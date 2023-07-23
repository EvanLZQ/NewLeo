from django.urls import path
from . import views

urlpatterns = [
    path('completeset', views.getCompleteSet, name='completeset'),
    path('createcompleteset', views.createCompleteSet, name='create_completeset'),
]
