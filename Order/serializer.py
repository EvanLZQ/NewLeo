from rest_framework import serializers
from .models import *
from Lens.serializer import *
from Product.serializer import ProductInstanceSerializer
from Lens.models import *
from Product.models import ProductInstance
from General.serializer import AddressSerializer
from Prescription.serializer import PrescriptionSerializer
from Prescription.models import PrescriptionInfo


class CompleteSetSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    color = serializers.CharField(source='color.name')
    usage = serializers.CharField(source='usage.name')
    coating = serializers.CharField(source='coating.name')
    index = serializers.CharField(source='index.name')
    frame = serializers.SerializerMethodField()
    density = serializers.CharField(
        source='density.name', required=False, allow_null=True, default=None)
    prescription = PrescriptionSerializer(
        required=False, allow_null=True)  # Return full nested data

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
            'prescription',
            'sub_color',
            'sub_total',
            'saved_for_later',
        ]

    def get_frame(self, obj):
        return obj.frame.sku

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        instance = ProductInstance.objects.get(sku=obj.frame)
        rep['frame'] = ProductInstanceSerializer(instance).data
        if not rep['sub_color']:
            rep['sub_color'] = "None"
        return rep

    def create(self, data):
        # print(self.context['request'].data)
        usage_name = data.pop('usage')['name']
        usage_obj = LensUsage.objects.get(name=usage_name)

        color_name = data.pop('color')['name']
        color_obj = LensColor.objects.get(name=color_name)

        index_name = data.pop('index')['name']
        index_obj = LensIndex.objects.get(name=index_name)

        coating_name = data.pop('coating')['name']
        coating_obj = LensCoating.objects.get(name=coating_name)

        frame_data = self.context['request'].data.get('frame')
        frame_obj = ProductInstance.objects.get(sku=frame_data['sku'])

        density_name = data.pop('density')['name']
        density_obj = LensDensity.objects.get(name=density_name)

        prescription_data = self.context['request'].data.get('prescription')
        prescription_obj = PrescriptionInfo.objects.get(
            id=prescription_data['id']) if prescription_data else None

        completeset = CompleteSet.objects.create(
            color=color_obj,
            usage=usage_obj,
            coating=coating_obj,
            frame=frame_obj,
            density=density_obj,
            index=index_obj,
            prescription=prescription_obj,
            sub_total=data.get('sub_total', 0)
        )

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
            frame_data = validated_data.get('frame')
            instance.frame = ProductInstance.objects.get(sku=frame_data['sku'])

        if 'density' in validated_data:
            density_name = validated_data.pop('density')['name']
            instance.density = LensDensity.objects.get(name=density_name)

        if 'saved_for_later' in validated_data:
            saved_for_later = validated_data.pop('saved_for_later')
            instance.saved_for_later = saved_for_later

        prescription_data = self.context['request'].data.get('prescription')
        if prescription_data:
            instance.prescription = PrescriptionInfo.objects.get(
                id=prescription_data['id'])
        else:
            # If explicitly null, clear the FK
            instance.prescription = None

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


class CompleteSetObjectSerializer(serializers.ModelSerializer):
    color = LensColorSerializer()
    usage = LensUsageSerializer()
    coating = LensCoatingSerializer()
    index = LensIndexSerializer()
    frame = serializers.SerializerMethodField()
    density = serializers.CharField(
        source='density.name', required=False, allow_null=True, default=None)
    prescription = PrescriptionSerializer(allow_null=True)

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
            'saved_for_later',
            'prescription',
        ]

    def get_frame(self, obj):
        return obj.frame.sku

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        instance = ProductInstance.objects.get(sku=obj.frame)
        rep['frame'] = ProductInstanceSerializer(instance).data
        if not rep['sub_color']:
            rep['sub_color'] = "None"
        return rep
