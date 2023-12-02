from django.urls import path
from . import views

urlpatterns = [
    # Below is for customer profile
    path("summary", views.get_user, name="user_summary"),
    path('create_user', views.createCustomer, name='create_user'),
    path('profile_brief', views.getCustomerProfile, name='user_profile_brief'),
    path('profile_update', views.updateCustomerProfile,
         name='user_profile_update'),
    path("get_store_credit_history", views.getCustomerStoreCreditActivity,
         name="get_store_credit_history"),
    path("upload_avatar", views.uploadCustomerAvatar, name="upload_avatar"),

    # Below is for shopping list
    path("shoppinglist/<int:list_id>",
         views.get_shopping_list, name='get_shopping_list'),
    path("shoppinglist/update/<int:list_id>",
         views.update_shopping_list, name='update_shopping_list'),
    path("shoppinglist/new", views.create_shopping_list,
         name='create_shopping_list'),
    path("shoppinglist/assign/<int:list_id>",
         views.assign_shopping_list, name='assign_shopping_list'),
    path("shoppinglist/delete/<int:list_id>",
         views.delete_shopping_list, name='delete_shopping_list'),

    # Below is for customer login & logout
    path("login", views.login_view, name='user_login'),
    path("logout", views.logout_view, name='user_logout'),
    path("googlelogin", views.google_login, name='google_login'),
    path('check_credential', views.is_authenticated, name='check_credential'),

    # Below is for customer order
    path("get_customer_order", views.getCustomerOrders, name="get_customer_order"),

    # Below is for customer prescription
    path("get_prescription", views.getCustomerPrescription, name="get_prescription"),
    path("update_prescription", views.updateCustomerPrescription,
         name="update_prescription"),
    path("add_prescription", views.addCustomerPrescription, name="add_prescription"),

    # Below is for customer address
    path("get_addresses", views.getCustomerAddress, name="get_addresses"),
    path("add_address", views.addCustomerAddress, name="add_address"),
    path("update_address/<int:address_id>",
         views.updateCustomerAddress, name="update_address"),
    path("delete_address/<int:address_id>",
         views.deleteCustomerAddress, name="delete_address"),

    # Below is for wish list
    path("get_user_wish_list", views.getUserWishList, name="get_user_wish_list"),
    path("get_wish_list/<int:list_id>",
         views.getTargetWishList, name="get_wish_list"),
    path("add_wish_list", views.addWishList, name="add_wish_list"),
    path("update_wish_list/<int:list_id>",
         views.updateWishList, name="update_wish_list"),
    path("delete_wish_list/<int:list_id>",
         views.deleteWishList, name="delete_wish_list"),
    path("assign_wish_list/<int:list_id>",
         views.assignWishList, name="assign_wish_list"),
]
