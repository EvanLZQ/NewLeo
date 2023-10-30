from rest_framework import serializers
from .models import Address, ImageUpload


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageUpload
        fields = '__all__'
