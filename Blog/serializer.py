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
    class Meta:
        model = BlogInfo
        fields = '__all__'
