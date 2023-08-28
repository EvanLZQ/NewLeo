from django.urls import path
from . import views

urlpatterns = [
    path('allorders', views.getAllOrders, name='orders'),
    path('<int:id>', views.getTargetOrder, name='get_target_order'),
    path('completeset', views.getCompleteSet, name='completesets'),
    path('createcompleteset', views.createCompleteSet, name='create_completeset'),
    path('completeset/<int:set_id>',
         views.getTargetCompleteSet, name='get_target_set'),
    path('updatecompleteset/<int:set_id>',
         views.updateCompleteSet, name='update_target_set'),
]
