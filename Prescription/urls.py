from django.urls import path
from .views import prescription_list_create, prescription_detail, fetch_prescriptions_by_ids_post

urlpatterns = [
    path("", prescription_list_create,
         name="prescription-list-create"),
    path("<int:pk>", prescription_detail,
         name="prescription-detail"),
    path("batch", fetch_prescriptions_by_ids_post,
         name="fetch-prescriptions-by-ids")
]
