from rest_framework import serializers
from .models import *
from .service.order_service import OrderService, get_complete_set_line_items
from lens_workflow.pricing import LensNotOffered
from lens_workflow.models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensReaderStrength,
)
from lens_workflow.serializers import (
    LensTypeSerializer,
    LensFunctionPathSerializer,
    LensIndexOptionSerializer,
    LensColorOptionSerializer,
    LensCoatingSerializer,
    LensReaderStrengthSerializer,
)
from Product.serializer import ProductInstanceSerializer
from Product.models import ProductInstance
from General.serializer import AddressSerializer
from Prescription.serializer import PrescriptionSerializer, PrescriptionUploadSerializer
from Prescription.models import PrescriptionInfo, PrescriptionUpload


def _attachable_prescription(request, rx_id):
    """A typed prescription the caller may put on a cart item: one this
    request owns (its account, this signed-out session, or one already on a
    cart item it owns; see Order/ownership.py). Anything else -- including
    another guest's Rx -- answers DoesNotExist, so it can't be attached and
    then read back via the cart. Staff get no bypass here."""
    from .ownership import get_owned_prescription
    rx = None
    if request is not None:
        rx = get_owned_prescription(request, rx_id, include_staff=False)
    if rx is None:
        raise PrescriptionInfo.DoesNotExist
    return rx


class _UploadField(serializers.PrimaryKeyRelatedField):
    """UUID string, or the read shape `{ "id": "<uuid>", ... }` sent back as is."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.get('id')
        return super().to_internal_value(data)


class CompleteSetSerializer(serializers.ModelSerializer):
    id       = serializers.IntegerField(required=False)
    # Frontend already knows the exact row id it picked at each workflow step
    # (from the lens_workflow API responses), so these are plain FK ids.
    lens_type     = serializers.PrimaryKeyRelatedField(queryset=LensType.objects.all(), required=False, allow_null=True)
    function_path = serializers.PrimaryKeyRelatedField(queryset=LensFunctionPath.objects.all(), required=False, allow_null=True)
    tint_type     = serializers.PrimaryKeyRelatedField(queryset=LensFunctionPath.objects.all(), required=False, allow_null=True)
    index_option  = serializers.PrimaryKeyRelatedField(queryset=LensIndexOption.objects.all(), required=False, allow_null=True)
    color_option  = serializers.PrimaryKeyRelatedField(queryset=LensColorOption.objects.all(), required=False, allow_null=True)
    coatings      = serializers.PrimaryKeyRelatedField(queryset=LensCoating.objects.all(), required=False, many=True)
    reader_strength = serializers.PrimaryKeyRelatedField(queryset=LensReaderStrength.objects.all(), required=False, allow_null=True)
    frame    = serializers.SerializerMethodField()
    # density is now a plain CharField on the model — no source traversal needed
    density  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    prescription = PrescriptionSerializer(required=False, allow_null=True)
    # Exposes the raw FK integer (or null) so the frontend can tell whether
    # this item is currently attached to a pending (UNPAID) order.
    order_id = serializers.IntegerField(read_only=True, allow_null=True)
    # Write: the upload's UUID (or null to detach). Read: the upload object.
    prescription_upload = _UploadField(
        queryset=PrescriptionUpload.objects.all(), required=False, allow_null=True)

    class Meta:
        model = CompleteSet
        fields = [
            'id',
            'frame',
            'lens_type',
            'function_path',
            'tint_type',
            'index_option',
            'color_option',
            'coatings',
            'reader_strength',
            'density',
            'prescription',
            'prescription_upload',
            'sub_color',
            'sub_total',
            'saved_for_later',
            'order_id',
        ]

    def get_frame(self, obj):
        return obj.frame.sku

    def validate_prescription_upload(self, upload):
        """Only the uploader (same account, or the same signed-out session)
        may attach an upload. Re-sending the upload this item already has is
        always fine (the Edit page sends it back unchanged)."""
        if upload is None:
            return upload
        if self.instance is not None and self.instance.prescription_upload_id == upload.pk:
            return upload
        from .ownership import caller_made_upload
        request = self.context.get('request')
        if request is None or not caller_made_upload(request, upload):
            raise serializers.ValidationError('Prescription upload not found.')
        return upload

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
        rep['tint_type']     = obj.tint_type.function_label if obj.tint_type else None
        rep['index_option']  = obj.index_option.option_label if obj.index_option else None
        rep['color_option']  = obj.color_option.color_name if obj.color_option else None
        rep['coatings']      = [c.label for c in obj.coatings.all()]
        rep['reader_strength'] = obj.reader_strength.label if obj.reader_strength else None
        rep['prescription_upload'] = (
            PrescriptionUploadSerializer(obj.prescription_upload).data
            if obj.prescription_upload_id else None)
        # Per-lens-feature prices for cart/order itemization (frame excluded —
        # rep['frame'] above already carries its own price).
        rep['price_breakdown'] = get_complete_set_line_items(obj)
        # lens_type above is relabelled to a display string, so the frontend
        # can't infer prescription-requirement from it — expose the real flag
        # separately (cart page uses this to skip the "confirm your
        # prescription" prompt for non-Rx lens types like readymade readers).
        rep['is_prescription_required'] = (
            obj.lens_type.is_prescription_required if obj.lens_type else None
        )
        # Open carts show the price checkout will charge. A pair already on
        # an order keeps the sub_total that was frozen at checkout.
        rep['lens_unavailable'] = None
        if obj.order_id is None:
            try:
                fresh = OrderService.calculate_complete_set_sub_total(obj)
            except LensNotOffered as exc:
                rep['lens_unavailable'] = str(exc)
                rep['sub_total'] = None
            else:
                rep['sub_total'] = f"{fresh:.2f}"
        return rep

    # ── create ───────────────────────────────────────────────────────────────

    def create(self, validated_data):
        request = self.context['request']

        frame_data = request.data.get('frame')
        frame_obj  = ProductInstance.objects.get(sku=frame_data['sku'])

        rx_data = request.data.get('prescription')
        try:
            rx_obj = _attachable_prescription(request, rx_data['id']) if rx_data else None
        except PrescriptionInfo.DoesNotExist:
            raise serializers.ValidationError({'prescription': 'Prescription not found'})

        # coatings is many-to-many — can't be passed into .create()'s
        # kwargs, needs .set() after the row exists.
        coatings = validated_data.get('coatings')

        from django.db import transaction
        try:
            with transaction.atomic():
                instance = CompleteSet.objects.create(
                    frame=frame_obj,
                    lens_type=validated_data.get('lens_type'),
                    function_path=validated_data.get('function_path'),
                    tint_type=validated_data.get('tint_type'),
                    index_option=validated_data.get('index_option'),
                    color_option=validated_data.get('color_option'),
                    reader_strength=validated_data.get('reader_strength'),
                    density=validated_data.get('density'),
                    prescription=rx_obj,
                    prescription_upload=validated_data.get('prescription_upload'),
                    sub_color=validated_data.get('sub_color'),
                    saved_for_later=validated_data.get('saved_for_later', False),
                    sub_total=validated_data.get('sub_total', 0),
                )
                if coatings:
                    instance.coatings.set(coatings)
        except LensNotOffered as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        if coatings:
            # CompleteSet.save() recomputes sub_total unconditionally, but on
            # this first save() (pre-INSERT) coatings can't be queried yet —
            # see calculate_complete_set_sub_total's `if complete_set.pk:`
            # guard — so the row is first written with a coatings-less total.
            # The m2m_changed signal (Order/signals.py) corrects it in the
            # DB right after .set() above, but that's a separate queryset
            # .update() call — it never touches this in-memory `instance`,
            # which is what to_representation() below (and build_price_check
            # in views.py) actually reads. Without this, the API response —
            # and the customer's charged total — silently excludes every
            # coating on create.
            instance.refresh_from_db()
        return instance

    # ── update ───────────────────────────────────────────────────────────────

    def update(self, instance, validated_data):
        instance.sub_color       = validated_data.get('sub_color',       instance.sub_color)
        instance.sub_total       = validated_data.get('sub_total',       instance.sub_total)
        instance.saved_for_later = validated_data.get('saved_for_later', instance.saved_for_later)

        for field in ('lens_type', 'function_path', 'tint_type', 'index_option', 'color_option', 'reader_strength', 'density', 'prescription_upload'):
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
                    if rx_id != instance.prescription_id:
                        instance.prescription = _attachable_prescription(
                            self.context['request'], rx_id)
                except (TypeError, KeyError):
                    raise serializers.ValidationError(
                        {'prescription': 'Expected object with { "id": <number> }'})
                except PrescriptionInfo.DoesNotExist:
                    raise serializers.ValidationError(
                        {'prescription': f'Prescription id {rx_id} not found'})

        from django.db import transaction
        try:
            with transaction.atomic():
                instance.save()
                if 'coatings' in validated_data:
                    instance.coatings.set(validated_data.get('coatings'))
                    instance.refresh_from_db()
        except LensNotOffered as exc:
            raise serializers.ValidationError({'detail': str(exc)})

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
            'customs_fee',
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
    tint_type     = LensFunctionPathSerializer(allow_null=True)
    index_option  = LensIndexOptionSerializer(allow_null=True)
    color_option  = LensColorOptionSerializer(allow_null=True)
    coatings      = LensCoatingSerializer(many=True)
    reader_strength = LensReaderStrengthSerializer(allow_null=True)
    frame    = serializers.SerializerMethodField()
    density  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    prescription = PrescriptionSerializer(allow_null=True)
    prescription_upload = PrescriptionUploadSerializer(allow_null=True, read_only=True)

    class Meta:
        model = CompleteSet
        fields = [
            'id',
            'frame',
            'lens_type',
            'function_path',
            'tint_type',
            'index_option',
            'color_option',
            'coatings',
            'reader_strength',
            'density',
            'sub_color',
            'sub_total',
            'saved_for_later',
            'prescription',
            'prescription_upload',
        ]

    def get_frame(self, obj):
        return obj.frame.sku

    def to_representation(self, obj):
        rep = super().to_representation(obj)
        rep['frame'] = ProductInstanceSerializer(obj.frame).data
        if not rep.get('sub_color'):
            rep['sub_color'] = 'None'
        return rep
