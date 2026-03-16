from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

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
    try:
        blog = BlogInfo.objects.get(id=blog_slug)
    except BlogInfo.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = BlogBriefSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getFirstBlogBrief(request):
    blog = BlogInfo.objects.first()
    serializer = BlogBriefSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getBlogDetails(request, blog_slug):
    try:
        blog = BlogInfo.objects.get(slug=blog_slug)
    except BlogInfo.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = BlogSerializer(blog)
    return Response(serializer.data)


@api_view(["GET"])
def getBlogsInEachCategory(request):
    # Single query — group by category in Python
    from collections import defaultdict
    blogs = BlogInfo.objects.all()
    grouped = defaultdict(list)
    for blog in blogs:
        grouped[blog.category].append(BlogBriefSerializer(blog).data)
    return Response(dict(grouped))
