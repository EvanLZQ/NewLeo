from rest_framework import serializers
from .models import ColorInfo


class ColorSerializer(serializers.ModelSerializer):

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = ColorInfo
        fields = [
            'id',
            'display_name',
            'base_name',
            'image_url',
        ]
