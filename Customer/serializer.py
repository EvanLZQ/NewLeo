from rest_framework import serializers
from .models import *
from General.serializer import AddressSerializer
from Product.serializer import *


class CustomerSavedPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerSavedPayment
        fields = [
            'payment_method_type',
            'token',
            'last4',
            'card_brand',
            'expiry_date',
        ]


class CustomerSavedAddresses(serializers.ModelSerializer):
    class Meta:
        model = CustomerSavedAddress
        fields = [
            'fullname',
            'phone',
            'address',
            'city',
            'province_state',
            'country',
            'post_code',
            'instruction',
        ]


class CustomerSerializer(serializers.ModelSerializer):
    # saved_addresses = CustomerSavedAddresses(many=True)
    # saved_payment_method = CustomerSavedPaymentSerializer(many=True)

    # def to_representation(self, obj):
    #     representation = super().to_representation(obj)
    #     if not obj.saved_payment_method.exists():
    #         representation['saved_payment_method'] = []
    #     if not obj.saved_addresses.exists():
    #         representation['saved_addresses'] = []
    #     return representation

    class Meta:
        model = CustomerInfo
        fields = '__all__'

        # [
        #     'username',
        #     'first_name',
        #     'last_name',
        #     'phone',
        #     'gender',
        #     'birth_date',
        #     'icon_url',
        #     'store_credit',
        #     'level',
        #     'created_at',
        #     'saved_addresses',
        #     'saved_payment_method',
        # ]


class ShoppingListSerializer(serializers.ModelSerializer):
    product = ProductInstanceSerializer()

    class Meta:
        model = ShoppingList
        fields = '__all__'
