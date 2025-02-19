from rest_framework import serializers
from .models import SupplierInfo


class SupplierSerializer(serializers.ModelSerializer):

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep.pop('created_at', None)
        rep.pop('updated_at', None)
        return rep

    class Meta:
        model = SupplierInfo
        fields = '__all__'
