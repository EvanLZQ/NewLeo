# your_app/services/order_service.py
from decimal import Decimal
from django.db.models import Sum
from django.apps import apps

# Flat surcharge for a prescription with Prism correction — matches the
# "Add Prism $27" text shown on the prescription form itself
# (PrescriptionForm.tsx). Not a lens_workflow-priced option (Prism lives on
# the Prescription, not on any CompleteSet FK), so it isn't in the loop
# below — added explicitly wherever line items/sub_total are built instead.
PRISM_SURCHARGE = Decimal("27.00")


# Shipping. Priority Shipping (7-15 business days) is free for orders of at
# least FREE_SHIPPING_THRESHOLD (USD, the order's sub_total) with fewer than
# FREE_SHIPPING_MAX_PAIRS pairs of glasses; UPS (Canada only, 5-10 business
# days) is never free. Times exclude lens processing (usually another 3-7
# business days). Keep UserSite/src/config/helper.ts shippingOptions in step.
SHIPPING_PRIORITY = "Priority Shipping"
SHIPPING_UPS = "UPS"
PRIORITY_SHIPPING_COST = Decimal("8.95")
UPS_SHIPPING_COST = Decimal("24.95")
FREE_SHIPPING_THRESHOLD = Decimal("59")
FREE_SHIPPING_MAX_PAIRS = 3


def has_prism(complete_set):
    """True when this CompleteSet's attached prescription has Prism values set."""
    return bool(
        complete_set.prescription_id
        and complete_set.prescription.prism.exists()
    )


def get_complete_set_line_items(complete_set):
    """
    Backend-authoritative {component, label, price} rows for every priced
    lens feature attached to this CompleteSet — frame excluded (shown
    separately everywhere this is used, since it isn't a lens_workflow FK).
    Shared by Order/views.py's build_price_check and
    Order/serializer.py's CompleteSetSerializer.price_breakdown (cart/order
    itemization). Lives here (not in views.py) so serializer.py can import
    it without a circular import — views.py already imports from serializer.py.

    When the lens price sheet is loaded, the stacked function/tint/index/color
    rows collapse into one all-in "lens" row. Prism and coatings the sheet
    does not price (Oleophobic, Hydrophobic) stay as their own rows.
    """
    from lens_workflow.pricing import line_items_for_complete_set
    sheet_items = line_items_for_complete_set(complete_set)
    if sheet_items is not None:
        return sheet_items
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
    if has_prism(complete_set):
        items.append({
            'component': 'prism',
            'label':     'Prism',
            'price':     float(PRISM_SURCHARGE),
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
                if order.coupon_used.applied_product.filter(sku=complete_set.frame.sku).exists():
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
    def calculate_order_discount(order, items_total):
        """
        The coupon's order-level discount, taken off the merchandise total
        after any per-item (frame/lens) discounts. Never more than that total.
        """
        items_total = Decimal(str(items_total))
        if not OrderService.is_coupon_applicable(order) or items_total <= 0:
            return Decimal('0')
        coupon = order.coupon_used
        amount = Decimal(str(coupon.order_discount_amount or 0))
        if amount <= 0:
            return Decimal('0')
        if coupon.order_discount_type == 'Percentage':
            discount = items_total * amount / Decimal('100')
        elif coupon.order_discount_type == 'Amount':
            discount = amount
        else:
            return Decimal('0')
        return min(items_total, discount).quantize(Decimal('0.01'))

    @staticmethod
    def calculate_items_total(order, complete_sets):
        """Sum of item prices after per-item (frame/lens) coupon discounts."""
        total = Decimal('0')
        for complete_set in complete_sets:
            frame_discount = OrderService.calculate_frame_discount(
                order, complete_set)
            lens_discount = OrderService.calculate_lens_discount(
                order, complete_set)
            total += max(Decimal('0'), Decimal(str(complete_set.sub_total)) -
                         Decimal(str(frame_discount)) - Decimal(str(lens_discount)))
        return total

    @staticmethod
    def complete_sets_for_order(order):
        """Pairs attached to a saved order.

        `CompleteSet.objects.filter(order=unsaved_order)` compiles to
        `order_id IS NULL`. OrderInfo.save() runs that lookup before the new
        order has a primary key, so it used to load every pair still sitting
        in a cart. Pricing one of those (a power the sheet does not sell)
        raised "Not offered for this prescription" and rolled back a checkout
        whose own pair was fine.
        """
        CompleteSet = apps.get_model('Order', 'CompleteSet')
        if getattr(order, 'pk', None) is None:
            return CompleteSet.objects.none()
        return CompleteSet.objects.filter(order_id=order.pk)

    @staticmethod
    def calculate_sub_total(order):
        complete_sets = OrderService.complete_sets_for_order(order)
        total = OrderService.calculate_items_total(order, complete_sets)
        return total - OrderService.calculate_order_discount(order, total)

    @staticmethod
    def normalize_shipping_method(country, shipping_method):
        """
        The two shipping options a customer can pick:
          * "Priority Shipping" (everyone)
          * "UPS" (Canada only)
        Anything else a client sends, including the names this checkout used
        before ("Primary express", "Xpresspost"), becomes Priority Shipping,
        and UPS requested for a US address is Priority Shipping too.
        """
        if country != "United States" and shipping_method == SHIPPING_UPS:
            return SHIPPING_UPS
        return SHIPPING_PRIORITY

    @staticmethod
    def calculate_shipping_cost(country, sub_total, shipping_method, pairs=0):
        """
        Priority Shipping: 8.95, free from FREE_SHIPPING_THRESHOLD of sub_total
        as long as the order has fewer than FREE_SHIPPING_MAX_PAIRS pairs of
        glasses. UPS (Canada only): flat 24.95, never free. Returns Decimal.
        """
        method = OrderService.normalize_shipping_method(country, shipping_method)
        if method == SHIPPING_UPS:
            return UPS_SHIPPING_COST
        if (Decimal(str(sub_total)) >= FREE_SHIPPING_THRESHOLD
                and pairs < FREE_SHIPPING_MAX_PAIRS):
            return Decimal('0')
        return PRIORITY_SHIPPING_COST

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
            # shipping_company holds the method the customer picked until
            # staff overwrite it with the real carrier when the order ships
            # (anything but "UPS" prices as Priority Shipping).
            pairs = OrderService.complete_sets_for_order(order).count()
            shipping_cost = OrderService.calculate_shipping_cost(
                country, order.sub_total, order.shipping_company, pairs)
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
        # Frame plus the lens. The lens comes from the price sheet when that
        # table has rows (all-in cell + prism + coatings the sheet does not
        # cover). An empty table keeps the old add-on stack and logs a
        # warning — see lens_workflow.pricing. Raises LensNotOffered when the
        # sheet is loaded and this pair cannot be made; callers that charge
        # a customer must turn that into a 400 and must not invent a price.
        from lens_workflow.pricing import lens_total_for_complete_set
        total_price = Decimal("0.00")
        if complete_set.frame and complete_set.frame.price:
            total_price += Decimal(str(complete_set.frame.price))
        total_price += lens_total_for_complete_set(complete_set)
        return total_price.quantize(Decimal("0.01"))
