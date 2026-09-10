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


# Fields PrismSerializer accepts on write, besides 'id'/'prescription' (set
# by _sync_prism itself, not taken from client input).
_PRISM_WRITABLE_FIELDS = [
    'horizontal_value_l', 'horizontal_direction_l',
    'horizontal_value_r', 'horizontal_direction_r',
    'vertical_value_l', 'vertical_direction_l',
    'vertical_value_r', 'vertical_direction_r',
]


class PrescriptionSerializer(serializers.ModelSerializer):
    # many=True/read_only=True on the OUTPUT side only (matches
    # PrescriptionPrism's FK-per-row shape) — DRF can't auto-write a nested
    # many=True serializer, so writes are handled manually in create()/
    # update() below via _sync_prism, reading 'prism' out of the raw request
    # body (self.initial_data) rather than through this field.
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
            'add_l',
            'add_r',
            'created_at',
            'updated_at',
        ]

    def _sync_prism(self, prescription, prism_data):
        """
        Replace whatever Prism row(s) this prescription has with the single
        row 'prism_data' describes (or with nothing, when prism_data is
        falsy — the customer unchecked "Add Prism" / never checked it).
        Delete-then-recreate rather than update-in-place: the form always
        submits its current full state, never a partial diff, so there's
        nothing to merge.
        """
        prescription.prism.all().delete()
        if not prism_data:
            return
        prism_serializer = PrismSerializer(data={
            'prescription': prescription.id,
            **{key: prism_data.get(key) for key in _PRISM_WRITABLE_FIELDS},
        })
        prism_serializer.is_valid(raise_exception=True)
        prism_serializer.save()

    def create(self, validated_data):
        prism_data = self.initial_data.get('prism')
        instance = super().create(validated_data)
        self._sync_prism(instance, prism_data)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # Partial updates (PATCH) may not touch prism at all — only sync
        # when the client actually sent a 'prism' key, so a save that isn't
        # about prism (e.g. renaming a saved prescription) can't accidentally
        # wipe existing prism data just because it omitted the key.
        if 'prism' in self.initial_data:
            self._sync_prism(instance, self.initial_data.get('prism'))
        return instance
