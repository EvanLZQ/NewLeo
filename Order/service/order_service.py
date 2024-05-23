# your_app/services/order_service.py
from django.db.models import Sum
from django.apps import apps


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
        lens_price = complete_set.calculate_sub_total() - frame_price
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
        if country == "United States":
            if sub_total < 59:
                primary_express, ups = 8.95, 19.95
            elif sub_total <= 100:
                primary_express, ups = 0, 14.95
            elif sub_total <= 150:
                primary_express, ups = 0, 9.95
            elif sub_total <= 200:
                primary_express, ups = 0, 4.95
            else:
                primary_express, ups = 0, 0
        else:
            if sub_total < 59:
                xpresspost, ups = 13.95, 24.95
            elif sub_total <= 100:
                xpresspost, ups = 0, 19.95
            elif sub_total <= 150:
                xpresspost, ups = 0, 14.95
            elif sub_total <= 200:
                xpresspost, ups = 0, 9.95
            else:
                xpresspost, ups = 0, 0

        if country == "United States":
            return primary_express if shipping_method == "Primary express" else ups
        else:
            return xpresspost if shipping_method == "Xpresspost" else ups

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

        # Calculate shipping cost if address is provided
        if order.address:
            country = order.address.country
            # Assuming shipping_company is used to store the shipping method
            shipping_method = order.shipping_company
            shipping_cost = OrderService.calculate_shipping_cost(
                country, order.sub_total, shipping_method)
            shipping_discount = OrderService.calculate_shipping_discount(
                order, shipping_cost)
            order.shipping_cost = max(0, shipping_cost - shipping_discount)
        else:
            order.shipping_cost = 0

        # Calculate total_amount
        order.total_amount = order.sub_total + order.shipping_cost

    @staticmethod
    def calculate_complete_set_sub_total(complete_set):
        total_price = 0
        # Check if complete_set.frame is not None
        if complete_set.frame:
            # Check if complete_set.frame.price is not None
            if complete_set.frame.price is not None:
                total_price += complete_set.frame.price
            else:
                # If complete_set.frame.price is None, get the price from the linked ProductInfo
                # Ensure there's a link to a ProductInfo and it has a price
                if complete_set.frame.product and complete_set.frame.product.price is not None:
                    total_price += complete_set.frame.product.price
        if complete_set.usage:
            total_price += complete_set.usage.add_on_price
        if complete_set.color:
            total_price += complete_set.color.add_on_price
        if complete_set.coating:
            total_price += complete_set.coating.add_on_price
        if complete_set.index:
            total_price += complete_set.index.add_on_price
        if complete_set.density:
            total_price += complete_set.density.add_on_price
        return total_price
