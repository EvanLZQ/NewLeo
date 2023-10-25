from django.urls import path
from . import views

urlpatterns = [
    path('brief', views.getBlogBrief, name='blog_brief'),
    path('all_blog', views.getAllBlogs, name='all_blogs'),
    path('blog/<int:blog_id>', views.getBlogDetails, name='blog_details'),
    path('home_page_blog', views.getFirstBlogBrief, name='home_page_blog'),
    path('target_blog_brief/<int:blog_id>',
         views.getTargetBlogBrief, name='target_blog_brief'),
]
