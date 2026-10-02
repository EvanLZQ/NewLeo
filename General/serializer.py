from rest_framework import serializers
from .models import Address, ImageUpload, Coupon, CurrencyConversion, FAQ, PageImage


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageUpload
        fields = '__all__'


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            'id',
            'code',
            'description',
            'img_url',
            'expire_date',
            'online',
            'applied_product',
            'valid_customer',
            'frame_discount_type',
            'frame_discount_amount',
            'lens_discount_type',
            'lens_discount_amount',
            'shipping_discount_type',
            'shipping_discount_amount',
            'order_discount_type',
            'order_discount_amount',
        ]


class CustomerCouponSerializer(serializers.ModelSerializer):
    """
    "My Coupons" (account page) read shape — deliberately narrower than
    CouponSerializer: that one includes `applied_product`/`valid_customer`
    as raw id lists, which would leak which *other* customers share a
    coupon's eligibility to any customer who can see it. `discounts`
    collapses the 4 independent discount dimensions (frame/lens/shipping/
    order) into only the ones actually non-zero, so the frontend doesn't
    have to repeat the percentage-vs-amount formatting per dimension.
    """
    discounts = serializers.SerializerMethodField()

    def get_discounts(self, obj):
        parts = []
        for label, dtype, amount in [
            ('Frame', obj.frame_discount_type, obj.frame_discount_amount),
            ('Lens', obj.lens_discount_type, obj.lens_discount_amount),
            ('Shipping', obj.shipping_discount_type, obj.shipping_discount_amount),
            ('Order', obj.order_discount_type, obj.order_discount_amount),
        ]:
            if amount and amount > 0:
                value = f"{amount}% off" if dtype == "Percentage" else f"${amount} off"
                parts.append({"label": label, "value": value})
        return parts

    class Meta:
        model = Coupon
        fields = [
            'id',
            'code',
            'description',
            'img_url',
            'expire_date',
            'discounts',
        ]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrencyConversion
        fields = [
            'id',
            'symbol',
            'currency',
            'rate',
        ]


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = '__all__'


class PageImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        if obj.image:
            return f'https://admin.eyelovewear.com{obj.image.url}'
        return None

    class Meta:
        model = PageImage
        fields = [
            'id',
            'title',
            'image',
            'page',
            'section',
            'order'
        ]
