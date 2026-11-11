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
        user.email = validated_data['username']   # sync inherited email field
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
    # Write-only: cart membership is submitted as a bare list of {id}
    # objects — update() below only ever reads `.id` off each entry. This
    # has to be declared separately from the read shape because
    # CompleteSetSerializer.to_representation() relabels lens_type /
    # function_path / index_option / color_option / coating as
    # human-readable strings for display, while those same field names are
    # PrimaryKeyRelatedField (expecting a plain integer id) when
    # CompleteSetSerializer validates input. Round-tripping a GET response
    # straight back into this field — which is exactly what the frontend
    # does when adding to cart — fails PK validation against the label
    # strings. See to_representation() below for the actual read shape.
    eyeglasses_set = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True)
    active_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = ShoppingCart
        fields = [
            'id',
            'eyeglasses_set',
            'active_subtotal',
            'created_at',
            'updated_at',
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Newest addition first — nothing else in this chain orders the
        # M2M read, so it otherwise falls back to arbitrary DB order.
        rep['eyeglasses_set'] = CompleteSetSerializer(
            instance.eyeglasses_set.order_by('-id'), many=True).data
        return rep

    def update(self, instance, validated_data):
        set_data = validated_data.pop('eyeglasses_set', [])
        request = self.context.get('request')

        # Security fix 2026-11-11: only items the caller already owns (in this
        # cart, on their own order, or created by them / this session and
        # not yet on an order) may be put in the cart. The old rule accepted
        # any item not on an order, so any account could pull another
        # shopper's item (and its prescription) into its cart by id.
        # Unowned or missing ids are skipped silently, same as before.
        from Order.ownership import owned_complete_sets
        wanted_ids = []
        for item in set_data:
            set_id = item.get('id')
            if isinstance(set_id, int) or (isinstance(set_id, str) and set_id.isdigit()):
                wanted_ids.append(int(set_id))
        if request is not None:
            allowed = set(owned_complete_sets(request).filter(
                id__in=wanted_ids).values_list('id', flat=True))
        else:
            allowed = set()
        already_in_cart = set(instance.eyeglasses_set.filter(
            id__in=wanted_ids).values_list('id', flat=True))
        keep = [i for i in wanted_ids if i in allowed or i in already_in_cart]

        instance.eyeglasses_set.clear()
        if keep:
            instance.eyeglasses_set.add(*CompleteSet.objects.filter(id__in=keep))

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance

    def get_active_subtotal(self, obj):
        return obj.active_sets_subtotal()


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
    product = ProductSerializer(many=True, required=False)

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
