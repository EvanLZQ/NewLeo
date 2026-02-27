from rest_framework import serializers
from .models import *
from lens_workflow.models import LensOption
from lens_workflow.serializers import LensOptionSerializer
from Product.serializer import ProductInstanceSerializer
from Product.models import ProductInstance
from General.serializer import AddressSerializer
from Prescription.serializer import PrescriptionSerializer
from Prescription.models import PrescriptionInfo


class CompleteSetSerializer(serializers.ModelSerializer):
    id       = serializers.IntegerField(required=False)
    usage    = serializers.CharField(source='usage.name',   required=False, allow_null=True, default=None)
    color    = serializers.CharField(source='color.name',   required=False, allow_null=True, allow_blank=True, default=None)
    coating  = serializers.CharField(source='coating.name', required=False, allow_null=True, default=None)
    index    = serializers.CharField(source='index.name',   required=False, allow_null=True, default=None)
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
            'usage',
            'color',
            'coating',
            'index',
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
        rep['frame'] = ProductInstanceSerializer(
            ProductInstance.objects.get(sku=obj.frame)
        ).data
        # Normalize None → "" for color: frontend sends empty string when no
        # color step applies (e.g. COLOR_TYPE = Clear).
        if rep.get('color') is None:
            rep['color'] = ''
        if not rep.get('sub_color'):
            rep['sub_color'] = 'None'
        return rep

    # ── private helper ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_option(val, option_type):
        """
        Resolve a lens option name to a LensOption FK instance.

        `val` arrives from validated_data as a nested dict {'name': '<string>'}
        for dotted-source CharField fields (usage/color/coating/index), or as a
        plain string / None.  Returns the matching LensOption or None when the
        name is empty (e.g. color == "" for Clear-type lenses).
        """
        name = val.get('name') if isinstance(val, dict) else val
        if not name:
            return None
        return LensOption.objects.get(name=name, option_type=option_type)

    # ── create ───────────────────────────────────────────────────────────────

    def create(self, validated_data):
        request = self.context['request']

        usage_obj   = self._resolve_option(validated_data.pop('usage',   None), 'COLOR_TYPE')
        color_obj   = self._resolve_option(validated_data.pop('color',   None), 'COLOR')
        coating_obj = self._resolve_option(validated_data.pop('coating', None), 'COATING')
        index_obj   = self._resolve_option(validated_data.pop('index',   None), 'INDEX')
        density     = validated_data.pop('density', None)   # stored as plain string

        frame_data = request.data.get('frame')
        frame_obj  = ProductInstance.objects.get(sku=frame_data['sku'])

        rx_data = request.data.get('prescription')
        rx_obj  = PrescriptionInfo.objects.get(id=rx_data['id']) if rx_data else None

        return CompleteSet.objects.create(
            frame=frame_obj,
            usage=usage_obj,
            color=color_obj,
            coating=coating_obj,
            index=index_obj,
            density=density,
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

        if 'usage'   in validated_data:
            instance.usage   = self._resolve_option(validated_data.pop('usage'),   'COLOR_TYPE')
        if 'color'   in validated_data:
            instance.color   = self._resolve_option(validated_data.pop('color'),   'COLOR')
        if 'coating' in validated_data:
            instance.coating = self._resolve_option(validated_data.pop('coating'), 'COATING')
        if 'index'   in validated_data:
            instance.index   = self._resolve_option(validated_data.pop('index'),   'INDEX')
        if 'density' in validated_data:
            instance.density = validated_data.pop('density')    # plain string
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
# Used by /completesetloader/<id>.  Returns full nested LensOption objects
# (id, code, name, add_on_price, metadata, …) instead of bare name strings.
# Previously used the five separate Lens*Serializers; all four FK fields now
# point to the same LensOption model so they all use LensOptionSerializer.

class CompleteSetObjectSerializer(serializers.ModelSerializer):
    usage    = LensOptionSerializer(allow_null=True)
    color    = LensOptionSerializer(allow_null=True)
    coating  = LensOptionSerializer(allow_null=True)
    index    = LensOptionSerializer(allow_null=True)
    frame    = serializers.SerializerMethodField()
    density  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
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
        rep['frame'] = ProductInstanceSerializer(
            ProductInstance.objects.get(sku=obj.frame)
        ).data
        if not rep.get('sub_color'):
            rep['sub_color'] = 'None'
        return rep
