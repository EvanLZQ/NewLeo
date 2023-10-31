from rest_framework import serializers
from .models import *


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


class ProductImageImageOnlySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        if obj.image:
            return f'http://admin.eyelovewear.com{obj.image.url}'
        return None

    class Meta:
        model = ProductImage
        fields = ['image']


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        if obj.image:
            return f'http://admin.eyelovewear.com{obj.image.url}'
        return None

    class Meta:
        model = ProductImage
        fields = ['image', 'alt', 'image_type']


class ProductInstanceSerializer(serializers.ModelSerializer):
    carousel_img = serializers.SerializerMethodField()
    detail_img = serializers.SerializerMethodField()
    color_img_url = serializers.SerializerMethodField()

    def get_carousel_img(self, obj):
        images = ProductImage.objects.filter(
            productInstance=obj, image_type='carousel')
        serialized_data = ProductImageSerializer(images, many=True).data
        return [item['image'] for item in serialized_data]

    def get_detail_img(self, obj):
        images = ProductImage.objects.filter(
            productInstance=obj, image_type='detail')
        serialized_data = ProductImageSerializer(images, many=True).data
        return [item['image'] for item in serialized_data]

    def get_color_img_url(self, obj):
        img_url = obj.color_img.color_img.url if obj.color_img else ''
        return f'http://admin.eyelovewear.com{img_url}'

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        rep.pop('id', None)
        rep.pop('product', None)
        return rep

    def create(self, validated_data):
        try:
            # Try to get an existing instance
            instance = ProductInstance.objects.get(sku=validated_data['sku'])
            return instance
        except ProductInstance.DoesNotExist:
            # If it doesn't exist, create a new one
            return super().create(validated_data)

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
    productReview = ProductReviewSerializer(many=True)

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
            'productReview',
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


class SKUtoModelSerializer(serializers.ModelSerializer):
    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ProductInfo
        fields = [
            'model_number',
            'name',
        ]
