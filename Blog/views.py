from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework import status

from .models import BlogInfo, BlogPreview
from .serializer import BlogBriefSerializer, BlogSerializer, BlogPreviewSerializer


@api_view(["GET"])
def getBlogBrief(request):
    blog = BlogInfo.objects.all()
    serializer = BlogBriefSerializer(blog, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(["GET"])
def getAllBlogs(request):
    blog = BlogInfo.objects.all()
    serializer = BlogSerializer(blog, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(["GET"])
def getTargetBlogBrief(request, blog_slug):
    try:
        # blog_slug is a slug (see urls.py's <slug:blog_slug> converter and
        # the parameter name) — this used to look it up by `id`, which
        # raised an uncaught ValueError on any real slug (500 instead of
        # the intended 404 JSON response).
        blog = BlogInfo.objects.get(slug=blog_slug)
    except BlogInfo.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = BlogBriefSerializer(blog, context={'request': request})
    return Response(serializer.data)


@api_view(["GET"])
def getFirstBlogBrief(request):
    blog = BlogInfo.objects.first()
    serializer = BlogBriefSerializer(blog, context={'request': request})
    return Response(serializer.data)


@api_view(["GET"])
def getBlogDetails(request, blog_slug):
    try:
        blog = BlogInfo.objects.get(slug=blog_slug)
    except BlogInfo.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = BlogSerializer(blog, context={'request': request})
    return Response(serializer.data)


@api_view(["GET"])
def getBlogsInEachCategory(request):
    # Single query — group by category in Python
    from collections import defaultdict
    blogs = BlogInfo.objects.all()
    grouped = defaultdict(list)
    for blog in blogs:
        grouped[blog.category].append(
            BlogBriefSerializer(blog, context={'request': request}).data)
    return Response(dict(grouped))


# ── Admin dual mobile/desktop preview ───────────────────────────────────────
# Write side: only a logged-in staff member (the person editing the post in
# Django admin) can stage a draft. Read side is deliberately open — the
# frontend's hidden preview route (eyelovewear.com, a different subdomain)
# fetches it cross-origin with no admin session of its own, same as every
# other public blog endpoint above. The token is an opaque UUID standing in
# for a real permission check: acceptable here because a preview row only
# ever holds the same kind of content a published post would, nothing
# private, and rows are overwritten in place rather than accumulating.

@api_view(["POST"])
@permission_classes([IsAdminUser])
def saveBlogPreview(request):
    token = request.data.get('token')
    instance = None
    if token:
        instance = BlogPreview.objects.filter(token=token).first()
    serializer = BlogPreviewSerializer(instance, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def getBlogPreview(request, token):
    try:
        preview = BlogPreview.objects.get(token=token)
    except (BlogPreview.DoesNotExist, ValueError):
        # ValueError: token isn't a well-formed UUID at all (bad link) —
        # DoesNotExist: well-formed but no matching row (expired/typo'd).
        # Both are "nothing to preview", not a server error.
        return Response({'error': 'Preview not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = BlogPreviewSerializer(preview)
    return Response(serializer.data)
