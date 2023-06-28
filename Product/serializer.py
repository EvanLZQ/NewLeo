from rest_framework import serializers
from .models import *


class ProductInstanceSerializer(serializers.ModelSerializer):
    carousel_img = serializers.SerializerMethodField()
    detail_img = serializers.SerializerMethodField()

    def get_carousel_img(self, obj):
        img_url = obj.carousel_img.split(',') if obj.carousel_img else []
        return img_url

    def get_detail_img(self, obj):
        img_url = obj.detail_img.split(',') if obj.detail_img else []
        return img_url

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        rep.pop('id', None)
        rep.pop('product', None)
        return rep

    class Meta:
        model = ProductInstance
        fields = ['slug',
                  'sku',
                  'stock',
                  'reduced_price',
                  'price',
                  'carousel_img',
                  'detail_img',
                  'color_img_url',
                  'color_base_name',
                  'color_display_name',
                  'description']


class ProductSerializer(serializers.ModelSerializer):
    productInstance = serializers.SerializerMethodField()

    def get_productInstance(self, obj):
        instances = obj.productInstance.filter(online=True)
        serializer = ProductInstanceSerializer(instances, many=True)
        return serializer.data

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ProductInfo
        fields = [
            'id',
            'model_number',
            'name',
            'price',
            'description',
            'frame_width',
            'lens_width',
            'bridge',
            'temple_length',
            'lens_height',
            'upper_wearable_width',
            'lower_wearable_width',
            'letter_size',
            'string_size',
            'frame_weight',
            'bifocal',
            'gender',
            'nose_pad',
            'frame_style',
            'pd_upper_range',
            'pd_lower_range',
            'productInstance',
        ]


class ProductReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductReview
        fields = [
            'slug',
            'title',
            'content',
            'online',
            'rating',
        ]


class TargetInstanceSerializer(serializers.ModelSerializer):
    productInstance = serializers.SerializerMethodField()
    productReview = ProductReviewSerializer(many=True)

    def get_productInstance(self, obj):
        sku = self.context['sku']
        instances = obj.productInstance.filter(online=True, sku=sku).first()
        serializer = ProductInstanceSerializer(instances, many=False)
        return [serializer.data]

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ProductInfo
        fields = [
            'id',
            'model_number',
            'name',
            'price',
            'description',
            'frame_width',
            'lens_width',
            'bridge',
            'temple_length',
            'lens_height',
            'upper_wearable_width',
            'lower_wearable_width',
            'letter_size',
            'string_size',
            'frame_weight',
            'bifocal',
            'gender',
            'nose_pad',
            'frame_style',
            'pd_upper_range',
            'pd_lower_range',
            'productInstance',
            'productReview',
        ]
