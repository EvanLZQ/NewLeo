from rest_framework import serializers

from Order.models import CompleteSet
from .models import *
from General.serializer import AddressSerializer
from Product.serializer import *
from Order.serializer import CompleteSetSerializer


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
    product = serializers.SerializerMethodField(read_only=True)
    product_ids = serializers.PrimaryKeyRelatedField(
        queryset=CompleteSet.objects.all(), many=True, write_only=True, source='product', required=False)
    product_data = CompleteSetSerializer(
        many=True, write_only=True, required=False)

    class Meta:
        model = ShoppingList
        fields = '__all__'

    def get_product(self, obj):
        # Serialize the CompleteSet objects with all their details
        return CompleteSetSerializer(obj.product.all(), many=True).data

    def create(self, validated_data):
        products_data = validated_data.pop('product_data', [])
        product_ids = validated_data.pop('product_ids', [])

        shopping_list = ShoppingList.objects.create(**validated_data)

        # Link existing products by IDs
        for product_id in product_ids:
            shopping_list.product.add(product_id)

        # Create new CompleteSet objects if full details are provided
        for product_data in products_data:
            product = CompleteSetSerializer().create(product_data)
            shopping_list.product.add(product)

        return shopping_list

    def update(self, instance, validated_data):
        products_data = validated_data.pop('product_data', None)
        product_ids = validated_data.pop('product_ids', None)

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # If product_ids are provided, update the related products
        if product_ids:
            instance.product.set(product_ids)

        # If full CompleteSet details are provided, create new products and add them.
        if products_data:
            for product_data in products_data:
                product = CompleteSetSerializer().create(product_data)
                instance.product.add(product)

        instance.save()
        return instance
