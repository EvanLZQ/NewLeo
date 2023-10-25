from rest_framework import serializers
from .models import BlogInfo


class BlogBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogInfo
        fields = [
            'id',
            'title',
            'brief',
            'sub_title',
            'home_page_img',
        ]


class BlogSerializer(serializers.ModelSerializer):
    html = serializers.SerializerMethodField()
    plain = serializers.SerializerMethodField()

    def get_html(self, instance):
        return str(instance.content.html)

    def get_plain(self, instance):
        return str(instance.content.plain)

    class Meta:
        model = BlogInfo
        fields = [
            'id',
            'title',
            'slug',
            'brief',
            'sub_title',
            'html',
            'plain',
        ]
