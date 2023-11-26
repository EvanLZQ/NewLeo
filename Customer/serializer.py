from rest_framework import serializers

from Order.models import CompleteSet
from .models import *
from General.serializer import AddressSerializer
from Product.serializer import *
from Order.serializer import CompleteSetSerializer

__all__ = ['CustomerProfileSerializer', 'CustomerSerializer', 'CustomerSavedPaymentSerializer',
           'CustomerSavedAddresses', 'ShoppingListSerializer', 'CustomerCreateSerializer', 'StoreCreditActivitySerializer']


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
            'store_credit',
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


class ShoppingListSerializer(serializers.ModelSerializer):
    # product = serializers.SerializerMethodField(read_only=True, required=True)
    product = CompleteSetSerializer(many=True, required=False)
    product_ids = serializers.PrimaryKeyRelatedField(
        queryset=CompleteSet.objects.all(), many=True, write_only=True, source='product', required=False)
    product_data = CompleteSetSerializer(
        many=True, write_only=True, required=False)

    class Meta:
        model = ShoppingList
        fields = '__all__'

    # def get_product(self, obj):
    #     # Serialize the CompleteSet objects with all their details
    #     return CompleteSetSerializer(obj.product.all(), many=True).data

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
        # products_data = validated_data.pop('product_data', None)
        # product_ids = validated_data.pop('product_ids', None)
        products_data = validated_data.pop('product', None)
        print(products_data)
        # p = self.context['request'].data['product']

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # If full CompleteSet details are provided, update or create products.
        if products_data:
            existing_product_ids = [p.id for p in instance.product.all()]
            print(existing_product_ids)
            for product_data in products_data:
                # print(product_data)
                product_id = int(product_data.get('id', 0))
                if product_id and product_id in existing_product_ids:
                    # Update existing product
                    product_instance = CompleteSet.objects.get(id=product_id)
                    CompleteSetSerializer().update(product_instance, product_data)
                else:
                    # Create new product
                    print(product_id)
                    product = CompleteSet.objects.get(id=product_id)
                    instance.product.add(product)

        # # If product_ids are provided, update the related products
        # if product_ids:
        #     print("product_id")
        #     instance.product.set(product_ids)

        # # If full CompleteSet details are provided, create new products and add them.
        # if products_data:
        #     print("product_data")
        #     for product_data in products_data:
        #         product = CompleteSetSerializer().create(product_data)
        #         instance.product.add(product)

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
