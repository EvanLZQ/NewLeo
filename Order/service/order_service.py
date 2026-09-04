# your_app/services/order_service.py
from decimal import Decimal
from django.db.models import Sum
from django.apps import apps


def get_complete_set_line_items(complete_set):
    """
    Backend-authoritative {component, label, price} rows for every priced
    lens feature attached to this CompleteSet — frame excluded (shown
    separately everywhere this is used, since it isn't a lens_workflow FK).
    Shared by Order/views.py's build_price_check and
    Order/serializer.py's CompleteSetSerializer.price_breakdown (cart/order
    itemization). Lives here (not in views.py) so serializer.py can import
    it without a circular import — views.py already imports from serializer.py.
    """
    items = []
    for component, option_obj, price_field, label_field in [
        ('function_path',   complete_set.function_path,   'extra_price', 'function_label'),
        ('tint_type',       complete_set.tint_type,        'extra_price', 'function_label'),
        ('index_option',    complete_set.index_option,     'price',       'option_label'),
        ('color_option',    complete_set.color_option,     'extra_price', 'color_name'),
        ('reader_strength', complete_set.reader_strength,  'price',       'label'),
    ]:
        if option_obj is None:
            continue
        items.append({
            'component': component,
            'label':     getattr(option_obj, label_field),
            'price':     float(getattr(option_obj, price_field)),
        })
    if complete_set.pk:
        for coating in complete_set.coatings.all():
            items.append({
                'component': f'coating_{coating.id}',
                'label':     coating.label,
                'price':     float(coating.price),
            })
    return items


class OrderService:
    @staticmethod
    def is_coupon_applicable(order):
        """
        Check if the coupon is applicable for the order.
        """
        if order.coupon_used:
            # Check if valid_customer is not empty and if the customer is in the valid_customer list
            if order.coupon_used.valid_customer.exists():
                if order.customer and order.coupon_used.valid_customer.filter(id=order.customer.id).exists():
                    return True
                else:
                    return False
            else:
                # valid_customer is empty, so the coupon applies to all customers
                return True
        return False

    @staticmethod
    def calculate_frame_discount(order, complete_set):
        frame_price = complete_set.frame.price if complete_set.frame and complete_set.frame.price else 0
        frame_discount = 0

        if OrderService.is_coupon_applicable(order):
            if order.coupon_used.applied_product.exists():
                if order.coupon_used.applied_product.filter(SKU=complete_set.frame.SKU).exists():
                    if order.coupon_used.frame_discount_type == 'Percentage':
                        frame_discount = frame_price * \
                            (order.coupon_used.frame_discount_amount / 100)
                    elif order.coupon_used.frame_discount_type == 'Amount':
                        frame_discount = order.coupon_used.frame_discount_amount
            else:
                if order.coupon_used.frame_discount_type == 'Percentage':
                    frame_discount = frame_price * \
                        (order.coupon_used.frame_discount_amount / 100)
                elif order.coupon_used.frame_discount_type == 'Amount':
                    frame_discount = order.coupon_used.frame_discount_amount

        return frame_discount

    @staticmethod
    def calculate_lens_discount(order, complete_set):
        frame_price = complete_set.frame.price if complete_set.frame and complete_set.frame.price else 0
        lens_price = OrderService.calculate_complete_set_sub_total(complete_set) - frame_price
        lens_discount = 0

        if OrderService.is_coupon_applicable(order):
            if order.coupon_used.lens_discount_type == 'Percentage':
                lens_discount = lens_price * \
                    (order.coupon_used.lens_discount_amount / 100)
            elif order.coupon_used.lens_discount_type == 'Amount':
                lens_discount = order.coupon_used.lens_discount_amount

        return lens_discount

    @staticmethod
    def calculate_sub_total(order):
        CompleteSet = apps.get_model('Order', 'CompleteSet')
        complete_sets = CompleteSet.objects.filter(order=order)
        total = 0
        for complete_set in complete_sets:
            frame_discount = OrderService.calculate_frame_discount(
                order, complete_set)
            lens_discount = OrderService.calculate_lens_discount(
                order, complete_set)
            total += max(0, complete_set.sub_total -
                         frame_discount - lens_discount)
        return total

    @staticmethod
    def calculate_shipping_cost(country, sub_total, shipping_method):
        # Return Decimal values so they are compatible with DecimalField arithmetic
        # (mixing float + Decimal raises TypeError in Python 3).
        if country == "United States":
            if sub_total < 59:
                primary_express, ups = Decimal('8.95'), Decimal('19.95')
            elif sub_total <= 100:
                primary_express, ups = Decimal('0'), Decimal('14.95')
            elif sub_total <= 150:
                primary_express, ups = Decimal('0'), Decimal('9.95')
            elif sub_total <= 200:
                primary_express, ups = Decimal('0'), Decimal('4.95')
            else:
                primary_express, ups = Decimal('0'), Decimal('0')
        else:
            if sub_total < 59:
                xpresspost, ups = Decimal('13.95'), Decimal('24.95')
            elif sub_total <= 100:
                xpresspost, ups = Decimal('0'), Decimal('19.95')
            elif sub_total <= 150:
                xpresspost, ups = Decimal('0'), Decimal('14.95')
            elif sub_total <= 200:
                xpresspost, ups = Decimal('0'), Decimal('9.95')
            else:
                xpresspost, ups = Decimal('0'), Decimal('0')

        if country == "United States":
            return primary_express if shipping_method == "Primary express" else ups
        else:
            return xpresspost if shipping_method == "Xpresspost" else ups

    @staticmethod
    def calculate_customs_fee(country, sub_total):
        # US-only import/customs surcharge: 15% of sub_total, $9 minimum.
        # Confirmed with the business owner — based on sub_total, same base
        # calculate_shipping_cost uses (pre-discount; discount is applied
        # separately, on top of the combined total — see update_order_totals
        # and the equivalent inline logic in Order/views.py's
        # createPendingOrder/createPendingOrderGuest).
        if country != "United States":
            return Decimal('0')
        return max(sub_total * Decimal('0.15'), Decimal('9'))

    @staticmethod
    def calculate_shipping_discount(order, shipping_cost):
        if order.coupon_used:
            if order.coupon_used.shipping_discount_type == 'Percentage':
                return shipping_cost * (order.coupon_used.shipping_discount_amount / 100)
            elif order.coupon_used.shipping_discount_type == 'Amount':
                return min(shipping_cost, order.coupon_used.shipping_discount_amount)
        return 0

    @staticmethod
    def update_order_totals(order):
        # Calculate sub_total
        order.sub_total = OrderService.calculate_sub_total(order)

        # Calculate shipping cost (and customs fee) if address is provided
        if order.address:
            country = order.address.country
            # Assuming shipping_company is used to store the shipping method
            shipping_method = order.shipping_company
            shipping_cost = OrderService.calculate_shipping_cost(
                country, order.sub_total, shipping_method)
            shipping_discount = OrderService.calculate_shipping_discount(
                order, shipping_cost)
            order.shipping_cost = max(0, shipping_cost - shipping_discount)
            order.customs_fee = OrderService.calculate_customs_fee(
                country, order.sub_total)
        else:
            order.shipping_cost = 0
            order.customs_fee = 0

        # Calculate total_amount
        order.total_amount = order.sub_total + order.shipping_cost + order.customs_fee

    @staticmethod
    def calculate_complete_set_sub_total(complete_set):
        total_price = 0
        if complete_set.frame:
            total_price += complete_set.frame.price
        if complete_set.function_path:
            total_price += complete_set.function_path.extra_price
        if complete_set.tint_type:
            total_price += complete_set.tint_type.extra_price
        if complete_set.index_option:
            total_price += complete_set.index_option.price
        if complete_set.color_option:
            total_price += complete_set.color_option.extra_price
        if complete_set.reader_strength:
            total_price += complete_set.reader_strength.price
        # coatings is a ManyToMany — only queryable once this instance has a
        # pk. During the very first save() (pre-INSERT), self.pk is still
        # None, so this contributes 0 for that one call; the m2m_changed
        # signal in Order/signals.py recalculates for real once coatings
        # are actually attached (which can only happen post-save anyway).
        if complete_set.pk:
            for coating in complete_set.coatings.all():
                total_price += coating.price
        # density is now a plain CharField — no add_on_price contribution
        return total_price
