from rest_framework import serializers

from .models import *

__all__ = ['PrescriptionSerializer', 'PrismSerializer']


class PrismSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionPrism
        fields = [
            'id',
            'prescription',
            'horizontal_value_l',
            'horizontal_direction_l',
            'horizontal_value_r',
            'horizontal_direction_r',
            'vertical_value_l',
            'vertical_direction_l',
            'vertical_value_r',
            'vertical_direction_r',
        ]


class PrescriptionSerializer(serializers.ModelSerializer):
    prism = PrismSerializer(many=True, read_only=True)

    class Meta:
        model = PrescriptionInfo
        fields = [
            'id',
            'nickname',
            'prism',
            'pd_l',
            'pd_r',
            'sphere_l',
            'sphere_r',
            'cylinder_l',
            'cylinder_r',
            'axis_l',
            'axis_r',
            'base_l',
            'base_r',
            'nv_add',
            'created_at',
            'updated_at',
        ]
