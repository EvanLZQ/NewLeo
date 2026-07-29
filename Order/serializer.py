from rest_framework import serializers
from .models import *
from lens_workflow.models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
)
from lens_workflow.serializers import (
    LensTypeSerializer,
    LensFunctionPathSerializer,
    LensIndexOptionSerializer,
    LensColorOptionSerializer,
    LensCoatingSerializer,
)
from Product.serializer import ProductInstanceSerializer
from Product.models import ProductInstance
from General.serializer import AddressSerializer
from Prescription.serializer import PrescriptionSerializer
from Prescription.models import PrescriptionInfo


class CompleteSetSerializer(serializers.ModelSerializer):
    id       = serializers.IntegerField(required=False)
    # Frontend already knows the exact row id it picked at each workflow step
    # (from the lens_workflow API responses), so these are plain FK ids.
    lens_type     = serializers.PrimaryKeyRelatedField(queryset=LensType.objects.all(), required=False, allow_null=True)
    function_path = serializers.PrimaryKeyRelatedField(queryset=LensFunctionPath.objects.all(), required=False, allow_null=True)
    index_option  = serializers.PrimaryKeyRelatedField(queryset=LensIndexOption.objects.all(), required=False, allow_null=True)
    color_option  = serializers.PrimaryKeyRelatedField(queryset=LensColorOption.objects.all(), required=False, allow_null=True)
    coating       = serializers.PrimaryKeyRelatedField(queryset=LensCoating.objects.all(), required=False, allow_null=True)
    frame    = serializers.SerializerMethodField()
    # density is now a plain CharField on the model — no source traversal needed
    density  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    prescription = PrescriptionSerializer(required=False, allow_null=True)
    # Exposes the raw FK integer (or null) so the frontend can tell whether
    # this item is currently attached to a pending (UNPAID) order.
    order_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = CompleteSet
        fields = [
            'id',
            'frame',
            'lens_type',
            'function_path',
            'index_option',
            'color_option',
            'coating',
            'density',
            'prescription',
            'sub_color',
            'sub_total',
            'saved_for_later',
            'order_id',
        ]

    def get_frame(self, obj):
        return obj.frame.sku

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep['frame'] = ProductInstanceSerializer(obj.frame).data
        if not rep.get('sub_color'):
            rep['sub_color'] = 'None'
        # Read side shows human-readable labels (matches the pre-rebuild
        # behaviour of these fields); writes still take plain FK ids via the
        # PrimaryKeyRelatedField declarations above.
        rep['lens_type']     = obj.lens_type.label if obj.lens_type else None
        rep['function_path'] = obj.function_path.function_label if obj.function_path else None
        rep['index_option']  = obj.index_option.option_label if obj.index_option else None
        rep['color_option']  = obj.color_option.color_name if obj.color_option else None
        rep['coating']       = obj.coating.label if obj.coating else None
        return rep

    # ── create ───────────────────────────────────────────────────────────────

    def create(self, validated_data):
        request = self.context['request']

        frame_data = request.data.get('frame')
        frame_obj  = ProductInstance.objects.get(sku=frame_data['sku'])

        rx_data = request.data.get('prescription')
        rx_obj  = PrescriptionInfo.objects.get(id=rx_data['id']) if rx_data else None

        return CompleteSet.objects.create(
            frame=frame_obj,
            lens_type=validated_data.get('lens_type'),
            function_path=validated_data.get('function_path'),
            index_option=validated_data.get('index_option'),
            color_option=validated_data.get('color_option'),
            coating=validated_data.get('coating'),
            density=validated_data.get('density'),
            prescription=rx_obj,
            sub_color=validated_data.get('sub_color'),
            saved_for_later=validated_data.get('saved_for_later', False),
            sub_total=validated_data.get('sub_total', 0),
        )

    # ── update ───────────────────────────────────────────────────────────────

    def update(self, instance, validated_data):
        instance.sub_color       = validated_data.get('sub_color',       instance.sub_color)
        instance.sub_total       = validated_data.get('sub_total',       instance.sub_total)
        instance.saved_for_later = validated_data.get('saved_for_later', instance.saved_for_later)

        for field in ('lens_type', 'function_path', 'index_option', 'color_option', 'coating', 'density'):
            if field in validated_data:
                setattr(instance, field, validated_data.get(field))
        if 'frame' in validated_data:
            instance.frame = ProductInstance.objects.get(
                sku=validated_data.get('frame')['sku'])

        # Prescription is always read from the raw request body (same pattern
        # as legacy) so that an explicit null correctly clears the FK.
        if 'prescription' in self.context['request'].data:
            rx_payload = self.context['request'].data.get('prescription')
            if rx_payload is None:
                instance.prescription = None
            else:
                try:
                    rx_id = rx_payload.get('id')
                    instance.prescription = PrescriptionInfo.objects.get(id=rx_id)
                except (TypeError, KeyError):
                    raise serializers.ValidationError(
                        {'prescription': 'Expected object with { "id": <number> }'})
                except PrescriptionInfo.DoesNotExist:
                    raise serializers.ValidationError(
                        {'prescription': f'Prescription id {rx_id} not found'})

        instance.save()
        return instance


# ── OrderSerializer ──────────────────────────────────────────────────────────

class OrderSerializer(serializers.ModelSerializer):
    complete_set = CompleteSetSerializer(source='completeset_set', many=True)
    address = AddressSerializer()

    class Meta:
        model = OrderInfo
        fields = [
            'id',
            'email',
            'order_number',
            'order_status',
            'refound_status',
            'refound_amount',
            'payment_status',
            'payment_type',
            'store_credit_used',
            'store_credit_gained',
            'shipping_company',
            'tracking_number',
            'shipping_cost',
            'discount',
            'accessory_total',
            'sub_total',
            'total_amount',
            'comment',
            'created_at',
            'updated_at',
            'product',
            'complete_set',
            'address',
        ]


# ── CompleteSetObjectSerializer ──────────────────────────────────────────────
# Used by /completesetloader/<id>.  Returns full nested lens_workflow objects
# (id, code/label, price, metadata, …) instead of bare ids.

class CompleteSetObjectSerializer(serializers.ModelSerializer):
    lens_type     = LensTypeSerializer(allow_null=True)
    function_path = LensFunctionPathSerializer(allow_null=True)
    index_option  = LensIndexOptionSerializer(allow_null=True)
    color_option  = LensColorOptionSerializer(allow_null=True)
    coating       = LensCoatingSerializer(allow_null=True)
    frame    = serializers.SerializerMethodField()
    density  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    prescription = PrescriptionSerializer(allow_null=True)

    class Meta:
        model = CompleteSet
        fields = [
            'id',
            'frame',
            'lens_type',
            'function_path',
            'index_option',
            'color_option',
            'coating',
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
        rep['frame'] = ProductInstanceSerializer(obj.frame).data
        if not rep.get('sub_color'):
            rep['sub_color'] = 'None'
        return rep
