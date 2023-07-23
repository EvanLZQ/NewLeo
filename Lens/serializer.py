from rest_framework import serializers
from .models import *

__all__ = ['LensUsageSerializer', 'LensColorSerializer',
           'LensDensitySerializer', 'LensCoatingSerializer',
           'LensIndexSerializer']


class LensUsageSerializer(serializers.ModelSerializer):
    available_next_lvl = serializers.SerializerMethodField()

    def get_available_next_lvl(self, obj):
        a_n_l = obj.available_next_lvl.split(
            ',') if obj.available_next_lvl else None
        return a_n_l

    class Meta:
        model = LensUsage
        fields = [
            'id',
            'name',
            'description',
            'image_url',
            'add_on_price',
            'available_next_lvl',
        ]


class LensColorSerializer(serializers.ModelSerializer):
    available_next_lvl = serializers.SerializerMethodField()
    available_colors = serializers.SerializerMethodField()

    def get_available_next_lvl(self, obj):
        a_n_l = obj.available_next_lvl.split(
            ',') if obj.available_next_lvl else None
        return a_n_l

    def get_available_colors(self, obj):
        a_c = obj.available_colors.split(',') if obj.available_colors else None
        return a_c

    class Meta:
        model = LensColor
        fields = [
            'id',
            'name',
            'description',
            'image_url',
            'add_on_price',
            'available_colors',
            'available_next_lvl',
        ]


class LensDensitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LensDensity
        fields = [
            'id',
            'name',
            'description',
            'image_url',
            'add_on_price',
        ]


class LensCoatingSerializer(serializers.ModelSerializer):
    available_next_lvl = serializers.SerializerMethodField()

    def get_available_next_lvl(self, obj):
        a_n_l = obj.available_next_lvl.split(
            ',') if obj.available_next_lvl else None
        return a_n_l

    class Meta:
        model = LensCoating
        fields = [
            'id',
            'name',
            'description',
            'image_url',
            'add_on_price',
            'available_next_lvl',
        ]


class LensIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensIndex
        fields = [
            'id',
            'name',
            'description',
            'image_url',
            'add_on_price',
        ]
