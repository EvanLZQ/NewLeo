from django.urls import path
# from rest_framework_simplejwt.views import (
#     TokenObtainPairView,
#     TokenRefreshView,
# )

from . import views

urlpatterns = [
    path("summary", views.get_user, name="user_summary"),
    path("shoppinglist/<int:list_id>",
         views.get_shopping_list, name='get_shopping_list'),
    path("shoppinglist/update/<int:list_id>",
         views.update_shopping_list, name='update_shopping_list'),
    path("shoppinglist/new", views.create_shopping_list,
         name='create_shopping_list'),
]
