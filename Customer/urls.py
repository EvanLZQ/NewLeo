from django.urls import path
from . import views

urlpatterns = [
    path("summary", views.get_user, name="user_summary"),
    path('create_user', views.createCustomer, name='create_user'),
    path('profile_brief', views.getCustomerProfile, name='user_profile_brief'),
    path('profile_update', views.updateCustomerProfile,
         name='user_profile_update'),
    path("shoppinglist/<int:list_id>",
         views.get_shopping_list, name='get_shopping_list'),
    path("shoppinglist/update/<int:list_id>",
         views.update_shopping_list, name='update_shopping_list'),
    path("shoppinglist/new", views.create_shopping_list,
         name='create_shopping_list'),
    path("login", views.login_view, name='user_login'),
    path("logout", views.logout_view, name='user_logout'),
    path("googlelogin", views.google_login, name='google_login'),
    path('check_credential', views.is_authenticated, name='check_credential'),
    path("get_customer_order", views.getCustomerOrders, name="get_customer_order"),
]
