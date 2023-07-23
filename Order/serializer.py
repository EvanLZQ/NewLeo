from rest_framework import serializers
from .models import *
from Lens.serializer import *
from Product.serializer import ProductInstanceSerializer
from Lens.models import *
from Product.models import ProductInstance


class CompleteSetSerializer(serializers.ModelSerializer):
    color = serializers.CharField(source='color.name')
    usage = serializers.CharField(source='usage.name')
    coating = serializers.CharField(source='coating.name')
    index = serializers.CharField(source='index.name')
    frame = serializers.CharField(source='frame.sku')
    density = serializers.CharField(
        source='density.name', required=False, allow_null=True, default=None)

    class Meta:
        model = CompleteSet
        fields = [
            'frame',
            'usage',
            'color',
            'coating',
            'index',
            'density',
            'sub_color',
            'sub_total',
        ]

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        instance = ProductInstance.objects.get(sku=obj.frame)
        rep['frame'] = ProductInstanceSerializer(instance).data
        if not rep['sub_color']:
            rep['sub_color'] = "None"
        return rep

    def create(self, data):
        usage_name = data.pop('usage')['name']
        usage_obj = LensUsage.objects.get(name=usage_name)

        color_name = data.pop('color')['name']
        color_obj = LensColor.objects.get(name=color_name)

        index_name = data.pop('index')['name']
        index_obj = LensIndex.objects.get(name=index_name)

        coating_name = data.pop('coating')['name']
        coating_obj = LensCoating.objects.get(name=coating_name)

        frame_sku = data.pop('frame')['sku']
        frame_obj = ProductInstance.objects.get(sku=frame_sku)

        density_name = data.pop('density')['name']
        density_obj = LensDensity.objects.get(name=density_name)

        completeset = CompleteSet.objects.create(
            color=color_obj, usage=usage_obj, coating=coating_obj, frame=frame_obj, density=density_obj, index=index_obj)

        return completeset
