from rest_framework import serializers
from .models import SupplierInfo


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierInfo
        fields = '__all__'
