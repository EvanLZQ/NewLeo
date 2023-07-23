from django.urls import path
# from rest_framework_simplejwt.views import (
#     TokenObtainPairView,
#     TokenRefreshView,
# )

from . import views

urlpatterns = [
    path("summary", views.get_user, name="cart"),
]
