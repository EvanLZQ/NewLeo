from rest_framework import serializers

from .models import BlogInfo, BlogPreview


def _absolute_media_url(obj_field, request):
    """
    Shared by every serializer below so home_page_img is always an absolute
    URL, the same way regardless of which endpoint served it. Previously
    BlogBriefSerializer hardcoded `https://admin.eyelovewear.com` while
    BlogSerializer (fields='__all__', no request context passed in from
    views.py) returned a bare relative path — fine for the detail page
    today only because it doesn't render that field, but a latent
    inconsistency the moment it does. build_absolute_uri also means this
    keeps working unmodified in any non-production deployment.
    """
    if not obj_field:
        return None
    if request is not None:
        return request.build_absolute_uri(obj_field.url)
    return obj_field.url


class BlogBriefSerializer(serializers.ModelSerializer):
    home_page_img = serializers.SerializerMethodField()

    def get_home_page_img(self, obj):
        return _absolute_media_url(obj.home_page_img, self.context.get('request'))

    class Meta:
        model = BlogInfo
        fields = [
            'id',
            'title',
            'slug',
            'category',
            'brief',
            'sub_title',
            'home_page_img',
        ]


class BlogSerializer(serializers.ModelSerializer):
    home_page_img = serializers.SerializerMethodField()

    def get_home_page_img(self, obj):
        return _absolute_media_url(obj.home_page_img, self.context.get('request'))

    class Meta:
        model = BlogInfo
        fields = [
            'id',
            'title',
            'category',
            'slug',
            'content',
            'sub_title',
            'brief',
            'home_page_img',
            'created_at',
            'updated_at',
        ]


class BlogPreviewSerializer(serializers.ModelSerializer):
    """
    Read/write shape for the admin's dual mobile/desktop preview draft.
    Deliberately mirrors BlogSerializer's field names (title/content/
    brief/home_page_img/...) so the frontend's preview route can reuse the
    exact same rendering component as a real blog post — see
    UserSite src/components/Blog/BlogContents.tsx and BlogPreview.tsx.
    """
    home_page_img = serializers.URLField(source='home_page_img_url', required=False, allow_null=True)

    class Meta:
        model = BlogPreview
        fields = [
            'token',
            'title',
            'category',
            'sub_title',
            'content',
            'brief',
            'home_page_img',
            'updated_at',
        ]
        read_only_fields = ['token', 'updated_at']
