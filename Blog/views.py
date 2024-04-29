from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.http import JsonResponse

from .models import *
from .serializer import *


@api_view(["GET"])
def getBlogBrief(request):
    blog = BlogInfo.objects.all()
    serializer = BlogBriefSerializer(blog, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getAllBlogs(request):
    blog = BlogInfo.objects.all()
    serializer = BlogSerializer(blog, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getTargetBlogBrief(request, blog_slug):
    blog = BlogInfo.objects.get(id=blog_slug)
    serializer = BlogBriefSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getFirstBlogBrief(request):
    blog = BlogInfo.objects.first()
    serializer = BlogBriefSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getBlogDetails(request, blog_slug):
    blog = BlogInfo.objects.get(slug=blog_slug)
    serializer = BlogSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getBlogsInEachCategory(request):
    categories = BlogInfo.objects.values_list('category', flat=True).distinct()
    result = {}
    for category in categories:
        blogs = BlogInfo.objects.filter(category=category)
        serializer = BlogBriefSerializer(blogs)
        result[category] = serializer.data
    return Response(result)
