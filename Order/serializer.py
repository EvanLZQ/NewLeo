from rest_framework import serializers
from .models import *
from Lens.serializer import *
from Product.serializer import ProductInstanceSerializer
from Lens.models import *
from Product.models import ProductInstance
from General.serializer import AddressSerializer


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
            'id',
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

    def update(self, instance, validated_data):
        # Handle the update for the main model fields
        instance.sub_color = validated_data.get(
            'sub_color', instance.sub_color)
        instance.sub_total = validated_data.get(
            'sub_total', instance.sub_total)

        # Handle the update for the related fields
        if 'usage' in validated_data:
            usage_name = validated_data.pop('usage')['name']
            instance.usage = LensUsage.objects.get(name=usage_name)

        if 'color' in validated_data:
            color_name = validated_data.pop('color')['name']
            instance.color = LensColor.objects.get(name=color_name)

        if 'index' in validated_data:
            index_name = validated_data.pop('index')['name']
            instance.index = LensIndex.objects.get(name=index_name)

        if 'coating' in validated_data:
            coating_name = validated_data.pop('coating')['name']
            instance.coating = LensCoating.objects.get(name=coating_name)

        if 'frame' in validated_data:
            frame_sku = validated_data.pop('frame')['sku']
            instance.frame = ProductInstance.objects.get(sku=frame_sku)

        if 'density' in validated_data:
            density_name = validated_data.pop('density')['name']
            instance.density = LensDensity.objects.get(name=density_name)

        instance.save()
        return instance


class OrderSerializer(serializers.ModelSerializer):
    complete_set = CompleteSetSerializer(source="completeset_set", many=True)
    address = AddressSerializer()

    class Meta:
        model = OrderInfo
        fields = [
            "id",
            "email",
            "order_number",
            "order_status",
            "refound_status",
            "refound_amount",
            "payment_status",
            "payment_type",
            "store_credit_used",
            "store_credit_gained",
            "shipping_company",
            "tracking_number",
            "shipping_cost",
            "discount",
            "accessory_total",
            "sub_total",
            "total_amount",
            "comment",
            "created_at",
            "updated_at",
            "product",
            "complete_set",
            "address"
        ]
