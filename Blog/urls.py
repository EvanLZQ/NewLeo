from django.urls import path
from . import views

urlpatterns = [
    path('brief', views.getBlogBrief, name='blog_brief'),
    path('all_blog', views.getAllBlogs, name='all_blogs'),
    path('blog/<int:blog_id>', views.getBlogDetails, name='blog_details'),
]
