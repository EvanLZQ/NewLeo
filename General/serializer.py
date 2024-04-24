from rest_framework import serializers
from .models import Address, ImageUpload, Coupon, CurrencyConversion, FAQ


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageUpload
        fields = '__all__'


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            'id',
            'code',
            'description',
            'img_url',
            'expire_date',
            'online',
            'applied_product',
            'valid_customer',
            'frame_discount_type',
            'frame_discount_amount',
            'lens_discount_type',
            'lens_discount_amount',
            'shipping_discount_type',
            'shipping_discount_amount',
            'order_discount_type',
            'order_discount_amount'
        ]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrencyConversion
        fields = [
            'id',
            'symbol',
            'currency',
            'rate',
        ]


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = '__all__'
