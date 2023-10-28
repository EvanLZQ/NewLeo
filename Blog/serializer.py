from rest_framework import serializers
from .models import BlogInfo


class BlogBriefSerializer(serializers.ModelSerializer):
    home_page_img = serializers.SerializerMethodField()

    def get_home_page_img(self, obj):
        if obj.home_page_img:
            return f'http://admin.eyelovewear.com{obj.home_page_img.url}'
        return None

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
        fields = '__all__'
        # fields = [
        #     'id',
        #     'title',
        #     'slug',
        #     'brief',
        #     'sub_title',
        #     'html',
        #     'plain',
        # ]
