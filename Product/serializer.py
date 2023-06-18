from rest_framework import serializers

from .models import *
from Supplier.serializer import SupplierSerializer


class ProductDimensionSerializer(serializers.ModelSerializer):

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ProductDimension
        fields = '__all__'


# class ProductImageSerializer(serializers.ModelSerializer):

#     def to_representation(self, instance):
#         rep = super().to_representation(instance)
#         rep.pop('created_at', None)
#         rep.pop('updated_at', None)
#         return rep

#     class Meta:
#         model = ProductImage
#         fields = [
#             'id',
#             'slug',
#             'image_type',
#             'name',
#             'image_url',
#             'description',
#         ]


class ProductSerializer(serializers.ModelSerializer):
    dimension = ProductDimensionSerializer(source="dimensionID", many=False)
    supplier = SupplierSerializer(source="supplierID", many=False)
    # productimage = ProductImageSerializer(many=True)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ProductInfo
        fields = [
            'id',
            'slug',
            'dimension',
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
            'supplier',
            # 'productimage',
        ]
