from django.urls import path
from .views import prescription_list_create, prescription_detail

urlpatterns = [
    path("", prescription_list_create,
         name="prescription-list-create"),
    path("<int:pk>", prescription_detail,
         name="prescription-detail"),
]
