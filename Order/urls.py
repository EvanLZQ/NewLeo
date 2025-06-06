from django.urls import path
from . import views

urlpatterns = [
    path('allorders', views.getAllOrders, name='orders'),
    path('<int:id>', views.getTargetOrder, name='get_target_order'),
    path('completeset', views.getCompleteSet, name='completesets'),
    path('createcompleteset', views.createCompleteSet, name='create_completeset'),
    path('deletecompleteset/<int:set_id>',
         views.deleteCompleteSet, name='delete_completeset'),
    path('completeset/<int:set_id>',
         views.getTargetCompleteSet, name='get_target_set'),
    path('completesetloader/<int:set_id>',
         views.getCompleteSetLoader, name='get_set_loader'),
    path('updatecompleteset/<int:set_id>',
         views.updateCompleteSet, name='update_target_set'),
]
