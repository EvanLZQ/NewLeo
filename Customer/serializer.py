from rest_framework import serializers

from Order.models import CompleteSet
from Product.models import ProductInfo
from .models import *
from General.serializer import AddressSerializer
from Product.serializer import *
from Order.serializer import CompleteSetSerializer

__all__ = ['CustomerProfileSerializer', 'CustomerSerializer', 'CustomerSavedPaymentSerializer',
           'CustomerSavedAddresses', 'ShoppingCartSerializer', 'CustomerCreateSerializer', 'StoreCreditActivitySerializer',
           'WishListSerializer']


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
    class Meta:
        model = CustomerInfo
        fields = [
            'username',
            'first_name',
            'last_name',
            'phone',
            'gender',
            'birth_date',
            'icon_url',
            'level',
        ]


class CustomerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerInfo
        fields = [
            'username',
            'password',
        ]

    def create(self, validated_data):
        user = CustomerInfo(**validated_data)
        user.password = make_password(validated_data['password'])
        user.save()
        return user


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerInfo
        fields = [
            'first_name',
            'last_name',
            'phone',
            'gender',
            'birth_date',
            'icon_url',
        ]


class ShoppingCartSerializer(serializers.ModelSerializer):
    eyeglasses_set = CompleteSetSerializer(many=True)

    class Meta:
        model = ShoppingCart
        fields = [
            'id',
            'eyeglasses_set',
            'created_at',
            'updated_at',
        ]

    def update(self, instance, validated_data):
        set_data = validated_data.pop('eyeglasses_set', [])
        instance.eyeglasses_set.clear()
        for set in set_data:
            set_id = set.get('id')
            complete_set_instance = CompleteSet.objects.get(
                id=set_id)
            instance.eyeglasses_set.add(complete_set_instance)

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance


class StoreCreditActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreCreditActivity
        fields = [
            'total_amount',
            'change_amount',
            'description',
            'created_at',
        ]


class WishListSerializer(serializers.ModelSerializer):
    product = ProductSerializer(many=True)

    class Meta:
        model = WishList
        fields = [
            'id',
            'product',
            'created_at',
            'updated_at',
        ]

    def update(self, instance, validated_data):
        # Handle the product field separately
        products_data = validated_data.pop('product', [])
        instance.product.clear()
        for product_data in products_data:
            product_model = product_data.get('model_number')
            product_instance = ProductInfo.objects.get(
                model_number=product_model)
            instance.product.add(product_instance)

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance
