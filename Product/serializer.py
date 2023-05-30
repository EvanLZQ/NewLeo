from rest_framework import serializers

from .models import *
from Supplier.serializer import SupplierSerializer


class ProductDimensionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDimension
        fields = '__all__'


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    dimensionID = ProductDimensionSerializer()
    supplierID = SupplierSerializer()
    productimage = ProductImageSerializer(many=True)

    class Meta:
        model = ProductInfo
        fields = [
            'id',
            'slug',
            'dimensionID',
            'model_number',
            'sku',
            'stock',
            'price',
            'reduced_price',
            'description',
            'letter_size',
            'string_size',
            'frame_weight',
            'bifocal',
            'material',
            'shape',
            'gender',
            'nose_pad',
            'frame_style',
            'pd_upper_range',
            'pd_lower_range',
            'supplierID',
            'productimage'
        ]
