from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from Prescription.testing import rx_via_api

from General.models import Address
from Order.models import CompleteSet, OrderInfo
from Order.serializer import OrderSerializer
from Order.service.order_service import OrderService
from Prescription.models import PrescriptionInfo, PrescriptionPrism
from lens_workflow import price_table as pt
from lens_workflow.models import (
    LensCoating,
    LensFunctionPath,
    LensIndexOption,
    LensType,
)
from lens_workflow.pricing import LensNotOffered, MAX_CYL_MESSAGE
from lens_workflow.tests import block, workbook
from Order.views import _detach_paid_order_address
from Product.models import ProductInfo, ProductInstance

User = get_user_model()


def _frame(sku, price):
    product = ProductInfo.objects.create(
        model_number=sku,
        price=price,
        letter_size='M',
        string_size='52-18-145',
        frame_weight=20,
        frame_width=140,
        lens_width=52,
        bridge=18,
        temple_length=145,
        lens_height=40,
        upper_wearable_width=130,
        lower_wearable_width=125,
        nose_pad='Standard',
        frame_style='Full-Rim',
    )
    return ProductInstance.objects.create(
        product=product,
        sku=sku,
        price=price,
        color_base_name='black',
        color_display_name='Black',
    )


def _address_fields(**overrides):
    fields = {
        'full_name': 'QA Test US',
        'phone': '123-456-7890',
        'address': '1 Main St',
        'city': 'Austin',
        'province_state': 'Texas (TX)',
        'country': 'United States',
        'post_code': '78701',
    }
    fields.update(overrides)
    return fields


class CustomsFeeTests(TestCase):
    def test_us_rate_and_minimum(self):
        self.assertEqual(
            OrderService.calculate_customs_fee('United States', Decimal('100')),
            Decimal('15.00'),
        )
        # 15% of $40 is $6, so the $9 minimum applies.
        self.assertEqual(
            OrderService.calculate_customs_fee('United States', Decimal('40')),
            Decimal('9'),
        )

    def test_other_countries_are_zero(self):
        self.assertEqual(
            OrderService.calculate_customs_fee('Canada', Decimal('100')),
            Decimal('0'),
        )
        self.assertEqual(
            OrderService.calculate_customs_fee('', Decimal('100')),
            Decimal('0'),
        )

    def test_us_ups_still_prices_as_priority(self):
        self.assertEqual(
            OrderService.normalize_shipping_method('United States', 'UPS'),
            'Priority Shipping',
        )
        self.assertEqual(
            OrderService.calculate_shipping_cost('United States', Decimal('100'), 'UPS', 1),
            Decimal('0'),
        )
        self.assertEqual(
            OrderService.calculate_shipping_cost('Canada', Decimal('100'), 'UPS', 1),
            Decimal('24.95'),
        )


class CreatePendingAddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='qa@example.com', password='test-pass-123')
        self.user.refresh_from_db()
        self.other = User.objects.create_user(
            username='other@example.com', password='test-pass-123')
        self.client = APIClient()
        self.client.force_login(self.user)
        self.frame = _frame('QA-100', Decimal('100.00'))

    def _set(self):
        complete_set = CompleteSet.objects.create(frame=self.frame)
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        return complete_set

    def _post(self, complete_set, **extra):
        body = {
            'complete_set_ids': [complete_set.id],
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
            'email': '',
        }
        body.update(extra)
        return self.client.post('/api/order/create_pending', body, format='json')

    def test_reuses_posted_address_id(self):
        saved = Address.objects.create(customer=self.user, **_address_fields())
        complete_set = self._set()

        first = self._post(complete_set, address_id=saved.id)
        self.assertEqual(first.status_code, 201, first.data)
        second = self._post(complete_set, address_id=saved.id)
        self.assertEqual(second.status_code, 201, second.data)

        self.assertEqual(Address.objects.filter(customer=self.user).count(), 1)
        self.assertEqual(
            OrderInfo.objects.get(pk=second.data['order_id']).address_id,
            saved.id,
        )
        self.assertEqual(Decimal(second.data['customs_fee']), Decimal('15.00'))
        self.assertEqual(Decimal(second.data['shipping_cost']), Decimal('0'))
        self.assertEqual(Decimal(second.data['total_amount']), Decimal('115.00'))

    def test_same_address_fields_do_not_insert_twice(self):
        complete_set = self._set()
        fields = _address_fields(full_name='Test4')

        first = self._post(complete_set, address_data=fields)
        self.assertEqual(first.status_code, 201, first.data)
        second = self._post(complete_set, address_data=dict(fields))
        self.assertEqual(second.status_code, 201, second.data)

        rows = Address.objects.filter(customer=self.user)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().full_name, 'Test4')
        self.assertEqual(
            OrderInfo.objects.get(pk=first.data['order_id']).address_id,
            OrderInfo.objects.get(pk=second.data['order_id']).address_id,
        )

    def test_trimmed_repost_matches_existing_row(self):
        Address.objects.create(
            customer=self.user, **_address_fields(full_name='Test4 '))
        complete_set = self._set()
        response = self._post(
            complete_set, address_data=_address_fields(full_name='Test4'))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Address.objects.filter(customer=self.user).count(), 1)

    def test_different_fields_insert_a_new_row(self):
        complete_set = self._set()
        first = self._post(complete_set, address_data=_address_fields(full_name='Home'))
        self.assertEqual(first.status_code, 201, first.data)
        # The first order still holds the item; cancel it the way a second
        # checkout does, by calling again with a different address.
        second = self._post(
            complete_set, address_data=_address_fields(full_name='Work', address='9 Side St'))
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(Address.objects.filter(customer=self.user).count(), 2)

    def test_other_customers_address_is_rejected(self):
        foreign = Address.objects.create(customer=self.other, **_address_fields())
        complete_set = self._set()
        response = self._post(complete_set, address_id=foreign.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Address.objects.filter(customer=self.user).count(), 0)
        self.assertFalse(OrderInfo.objects.filter(customer=self.user).exists())

    def test_us_ups_request_does_not_charge_ups(self):
        saved = Address.objects.create(customer=self.user, **_address_fields())
        complete_set = self._set()
        response = self._post(
            complete_set, address_id=saved.id, shipping_method='UPS')
        self.assertEqual(response.status_code, 201, response.data)
        order = OrderInfo.objects.get(pk=response.data['order_id'])
        self.assertEqual(order.shipping_company, 'Priority Shipping')
        self.assertEqual(order.shipping_cost, Decimal('0.00'))
        self.assertEqual(order.customs_fee, Decimal('15.00'))

    def test_canada_has_no_customs_fee(self):
        saved = Address.objects.create(
            customer=self.user,
            **_address_fields(
                city='Toronto', province_state='Ontario (ON)',
                country='Canada', post_code='M5V 2T6'))
        complete_set = self._set()
        response = self._post(
            complete_set, address_id=saved.id, country='Canada',
            shipping_method='UPS')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data['customs_fee']), Decimal('0'))
        self.assertEqual(Decimal(response.data['shipping_cost']), Decimal('24.95'))

    def test_small_us_order_uses_customs_minimum(self):
        cheap = _frame('QA-40', Decimal('40.00'))
        complete_set = CompleteSet.objects.create(frame=cheap)
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        saved = Address.objects.create(customer=self.user, **_address_fields())
        response = self._post(complete_set, address_id=saved.id)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data['customs_fee']), Decimal('9.00'))
        self.assertEqual(Decimal(response.data['shipping_cost']), Decimal('8.95'))
        self.assertEqual(Decimal(response.data['total_amount']), Decimal('57.95'))

    def test_order_payload_includes_customs_fee(self):
        self.assertIn('customs_fee', OrderSerializer.Meta.fields)

    def test_paid_snapshot_is_not_a_saved_address(self):
        saved = Address.objects.create(customer=self.user, **_address_fields())
        frozen = _detach_paid_order_address(saved)
        self.assertIsNone(frozen.customer_id)
        self.assertNotEqual(frozen.id, saved.id)
        self.assertEqual(frozen.full_name, saved.full_name)
        self.assertEqual(Address.objects.filter(customer=self.user).count(), 1)
        self.assertEqual(_detach_paid_order_address(frozen).id, frozen.id)


class OrderLevelCouponTests(TestCase):
    """Coupon.order_discount_* used to be shown to customers but never applied."""

    def setUp(self):
        from General.models import Coupon
        self.user = User.objects.create_user(
            username='coupon@example.com', password='test-pass-123')
        self.user.refresh_from_db()
        self.client = APIClient()
        self.client.force_login(self.user)
        self.frame = _frame('QA-CPN-1', Decimal('50.00'))
        self.coupon = Coupon.objects.create(
            code='TENOFF', online=True,
            order_discount_type='Percentage', order_discount_amount=Decimal('10'))
        self.address = Address.objects.create(
            customer=self.user, **_address_fields(country='Canada',
                                                  province_state='Ontario (ON)',
                                                  city='Toronto', post_code='M5V 2T6'))

    def _set(self):
        complete_set = CompleteSet.objects.create(frame=self.frame)
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        return complete_set

    def test_validate_coupon_previews_order_discount(self):
        complete_set = self._set()
        res = self.client.post('/api/order/validate_coupon',
                               {'code': 'tenoff', 'complete_set_ids': [complete_set.id]},
                               format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data['discount_amount']), Decimal('5.00'))

    def test_create_pending_applies_and_stores_order_discount(self):
        complete_set = self._set()
        res = self.client.post('/api/order/create_pending', {
            'complete_set_ids': [complete_set.id], 'address_id': self.address.id,
            'shipping_method': 'Priority Shipping', 'country': 'Canada', 'email': '',
            'coupon_code': 'TENOFF',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(Decimal(res.data['sub_total']), Decimal('45.00'))
        # $45 is under the $59 free-shipping threshold.
        self.assertEqual(Decimal(res.data['shipping_cost']), Decimal('8.95'))
        self.assertEqual(Decimal(res.data['total_amount']), Decimal('53.95'))
        self.assertEqual(Decimal(res.data['discount_amount']), Decimal('5.00'))
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.discount, Decimal('5.00'))

    def test_amount_discount_never_exceeds_items(self):
        self.coupon.order_discount_type = 'Amount'
        self.coupon.order_discount_amount = Decimal('500')
        self.coupon.save()
        order = OrderInfo(customer=self.user, coupon_used=self.coupon)
        self.assertEqual(
            OrderService.calculate_order_discount(order, Decimal('50.00')),
            Decimal('50.00'))

    def test_coupon_without_order_discount_changes_nothing(self):
        self.coupon.order_discount_amount = Decimal('0')
        self.coupon.save()
        order = OrderInfo(customer=self.user, coupon_used=self.coupon)
        self.assertEqual(
            OrderService.calculate_order_discount(order, Decimal('50.00')),
            Decimal('0'))

    def test_discount_over_999_dollars_is_stored(self):
        # discount used to be numeric(5,2). Checkout now persists the combined
        # savings; $1,200 on two pairs must not overflow that column and roll
        # the order back.
        OrderInfo._meta.get_field('discount').clean(Decimal('1200.00'), None)
        self.frame.price = Decimal('600.00')
        self.frame.save()
        self.coupon.order_discount_amount = Decimal('100')
        self.coupon.save()
        first = self._set()
        second = self._set()
        res = self.client.post('/api/order/create_pending', {
            'complete_set_ids': [first.id, second.id],
            'address_id': self.address.id,
            'shipping_method': 'Priority Shipping',
            'country': 'Canada',
            'email': '',
            'coupon_code': 'TENOFF',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(Decimal(res.data['sub_total']), Decimal('0.00'))
        self.assertEqual(Decimal(res.data['discount_amount']), Decimal('1200.00'))
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.discount, Decimal('1200.00'))


def _svd_catalog():
    lens_type = LensType.objects.create(
        code='SVD', label='Single Vision Distance', is_prescription_required=True)
    clear = LensFunctionPath.objects.create(
        lens_type=lens_type, function_code='CLEAR', function_label='Classic',
        extra_price=Decimal('0'))
    blue = LensFunctionPath.objects.create(
        lens_type=lens_type, function_code='BLUE_LIGHT_FILTERING',
        function_label='Blue Light Filtering', extra_price=Decimal('9.95'))
    index = LensIndexOption.objects.create(
        lens_type=lens_type, tier='Basic', option_label='Basic - 1.50 Index',
        index_value=Decimal('1.50'), price=Decimal('4.95'))
    return lens_type, clear, blue, index


def _import_clear_sheet():
    """Premium clear 1.50 plano is 9.95. Blue-light clear 1.50 plano is 14.95.
    Economic clear 1.50 is 4.95 and is only used when Premium has no cell."""
    prem = (block(index=1.5, prices=[[9.95, 9.95, 9.95]] * 3)
            + block(index=1.5, coating='Blue Light Filtering',
                    prices=[[14.95, 14.95, 14.95]] * 3))
    pt.apply_import(pt.parse_workbook(workbook({
        'Premium Lens': prem,
        'Economic Lens': block(index=1.5, prices=[[4.95, 4.95, 4.95]] * 3),
    })), filename='checkout.xlsx', file_bytes=b'x')


class LensSheetCheckoutTests(TestCase):
    """Quote, cart sub_total, and the charged order total use one price."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='lens@example.com', password='test-pass-123')
        self.user.refresh_from_db()
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.client.force_login(self.user)
        self.frame = _frame('QA-LENS', Decimal('100.00'))
        self.lens_type, self.clear, self.blue, self.index = _svd_catalog()
        self.rx = PrescriptionInfo.objects.create()
        self.address = Address.objects.create(customer=self.user, **_address_fields())

    def _set(self, **extra):
        fields = dict(
            frame=self.frame, lens_type=self.lens_type, function_path=self.clear,
            index_option=self.index, prescription=self.rx)
        fields.update(extra)
        complete_set = CompleteSet.objects.create(**fields)
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        return complete_set

    def _checkout(self, complete_set):
        return self.client.post('/api/order/create_pending', {
            'complete_set_ids': [complete_set.id],
            'address_id': self.address.id,
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
            'email': '',
            'sub_total': '1.00',
        }, format='json')

    def test_empty_table_keeps_the_old_stack_and_logs(self):
        with self.assertLogs('lens_workflow.pricing', level='WARNING') as logs:
            complete_set = self._set()
        self.assertEqual(complete_set.sub_total, Decimal('104.95'))
        self.assertTrue(any('price table is empty' in line for line in logs.output))
        response = self._checkout(complete_set)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data['sub_total']), Decimal('104.95'))
        # Shipping rules are unchanged: US, subtotal over $59, one pair.
        self.assertEqual(Decimal(response.data['shipping_cost']), Decimal('0'))
        self.assertEqual(
            Decimal(response.data['customs_fee']),
            OrderService.calculate_customs_fee('United States', Decimal('104.95')))

    def test_checkout_charges_the_sheet_price_not_the_client_or_the_old_stack(self):
        _import_clear_sheet()
        complete_set = self._set()
        # Old stack would be frame 100 + index 4.95 = 104.95. The sheet cell is 9.95.
        self.assertEqual(complete_set.sub_total, Decimal('109.95'))
        CompleteSet.objects.filter(pk=complete_set.pk).update(sub_total=Decimal('1.00'))
        response = self._checkout(complete_set)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data['sub_total']), Decimal('109.95'))
        self.assertEqual(Decimal(response.data['shipping_cost']), Decimal('0'))
        self.assertEqual(
            Decimal(response.data['customs_fee']),
            OrderService.calculate_customs_fee('United States', Decimal('109.95')))
        complete_set.refresh_from_db()
        from Order.service.order_service import get_complete_set_line_items
        items = get_complete_set_line_items(complete_set)
        self.assertEqual(items[0]['component'], 'lens')
        self.assertEqual(items[0]['price'], 9.95)
        self.assertEqual(
            Decimal(str(self.frame.price)) + Decimal(str(sum(row['price'] for row in items))),
            complete_set.sub_total)

    def test_blue_light_is_inside_the_cell_and_oleophobic_is_not(self):
        _import_clear_sheet()
        oleo = LensCoating.objects.create(
            code='OLEOPHOBIC', label='Oleophobic', price=Decimal('4.95'))
        complete_set = self._set(function_path=self.blue)
        complete_set.coatings.add(oleo)
        complete_set.refresh_from_db()
        # Sheet blue-light cell 14.95 + oleophobic 4.95 + frame 100.
        # The old blue-light add-on ($9.95) is not added on top of the cell.
        self.assertEqual(complete_set.sub_total, Decimal('119.90'))

    def test_prism_stays_because_the_sheet_does_not_price_it(self):
        _import_clear_sheet()
        PrescriptionPrism.objects.create(
            prescription=self.rx, horizontal_value_r=Decimal('1.00'),
            horizontal_direction_r='In')
        complete_set = self._set()
        self.assertEqual(complete_set.sub_total, Decimal('136.95'))

    def test_max_cylinder_is_refused_at_checkout(self):
        _import_clear_sheet()
        self.rx.cylinder_r = Decimal('-6.25')
        self.rx.save()
        with self.assertRaises(LensNotOffered) as caught:
            self._set()
        self.assertEqual(str(caught.exception), MAX_CYL_MESSAGE)

    def test_index_missing_from_the_sheet_cannot_be_checked_out(self):
        # Saved under the empty-table fallback, then the sheet arrives.
        odd = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier='Safety', option_label='Safety - 1.59 Index',
            index_value=Decimal('1.59'), price=Decimal('19.95'))
        complete_set = self._set(index_option=odd)
        self.assertEqual(complete_set.sub_total, Decimal('119.95'))
        _import_clear_sheet()
        response = self._checkout(complete_set)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('not on the price sheet', response.data['error'])
        self.assertFalse(OrderInfo.objects.filter(customer=self.user).exists())


class PlanoGuestCheckoutTests(TestCase):
    """The production failure: a priced plano pair could not check out.

    OrderInfo.save() prices every complete set on the order before the order
    row exists. That query is `order_id IS NULL`, so it also priced every
    other cart. One unpriced pair refused checkout for a pair the quote,
    summary, and cart had already priced.
    """

    @classmethod
    def setUpTestData(cls):
        pt.apply_import(pt.parse_workbook(workbook({
            'Premium Lens': block(index=1.5, prices=[[9.95, 9.95, 9.95]] * 3),
            'Economic Lens': block(index=1.5, prices=[[4.95, 4.95, 4.95]] * 3),
        })), filename='plano.xlsx', file_bytes=b'x')
        cls.lens_type = LensType.objects.create(
            code='SVD', label='Single Vision Distance',
            is_prescription_required=True, is_active=True, sort_order=10)
        cls.function = LensFunctionPath.objects.create(
            lens_type=cls.lens_type, function_code='CLEAR', function_label='Classic',
            color_required=False, extra_price=Decimal('0'), is_active=True)
        cls.index = LensIndexOption.objects.create(
            lens_type=cls.lens_type, tier='Basic', option_label='Basic - 1.50 Index',
            index_value=Decimal('1.50'), price=Decimal('4.95'), is_active=True)

    def setUp(self):
        self.client = APIClient()
        self.client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        self.frame = _frame('CHY-MTL-ROU-88198-C2', Decimal('35.00'))

    def _workflow_ids(self):
        start = self.client.get('/api/lens-workflow/start/')
        self.assertEqual(start.status_code, 200, start.content)
        svd = next(opt for opt in start.data['options'] if opt['code'] == 'SVD')
        functions = self.client.get('/api/lens-workflow/next/', {
            'current_step_code': 'LENS_TYPE',
            'selected_option_id': svd['id'],
        })
        self.assertEqual(functions.status_code, 200, functions.content)
        classic = next(opt for opt in functions.data['options'] if opt['code'] == 'CLEAR')
        indexes = self.client.get('/api/lens-workflow/next/', {
            'current_step_code': 'FUNCTION',
            'selected_option_id': classic['id'],
            'selection_path': str(svd['id']),
        })
        self.assertEqual(indexes.status_code, 200, indexes.content)
        self.assertEqual(indexes.data['current_step']['code'], 'INDEX')
        basic = next(
            opt for opt in indexes.data['options']
            if opt['metadata']['index_value'] == '1.50')
        return svd['id'], classic['id'], basic['id']

    def _plano_pair(self, *, sphere='0'):
        lens_type_id, function_id, index_id = self._workflow_ids()
        quote = self.client.post('/api/lens-workflow/rx-quote/', {
            'od': {'sph': sphere, 'cyl': '0', 'add': '0', 'pd': '32'},
            'os': {'sph': sphere, 'cyl': '0', 'add': '0', 'pd': '31.5'},
            'lens_type_id': lens_type_id,
            'function_path_id': function_id,
            'index_option_id': index_id,
            'price': '1.00',
        }, format='json')
        self.assertEqual(quote.status_code, 200, quote.content)
        self.assertEqual(quote.data['pricing_source'], 'price_table')
        self.assertEqual(quote.data['selection']['lens_price'], '9.95')
        self.assertEqual(quote.data['total_lens_price'], '9.95')
        summary = self.client.get('/api/lens-workflow/summary/', {
            'lens_type_id': lens_type_id,
            'function_path_id': function_id,
            'index_option_id': index_id,
            'od_sph': sphere, 'od_cyl': '0', 'os_sph': sphere, 'os_cyl': '0',
        })
        self.assertEqual(summary.status_code, 200, summary.content)
        self.assertEqual(summary.data['pricing_source'], 'price_table')
        self.assertEqual(summary.data['total_add_on_price'], '9.95')
        rx = rx_via_api(self.client, 
            sphere_r=Decimal(sphere), sphere_l=Decimal(sphere),
            cylinder_r=Decimal('0'), cylinder_l=Decimal('0'),
            pd_r=Decimal('32'), pd_l=Decimal('31.50'))
        created = self.client.post('/api/order/createcompleteset', {
            'frame': {'sku': self.frame.sku},
            'lens_type': lens_type_id,
            'function_path': function_id,
            'index_option': index_id,
            'prescription': {'id': rx.id},
            'sub_total': '1.00',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        return created.data

    def _guest_address(self):
        return {
            'full_name': 'Guest Plano',
            'phone': '123-456-7890',
            'address': '1 Main St',
            'city': 'Austin',
            'province_state': 'Texas (TX)',
            'country': 'United States',
            'post_code': '78701',
        }

    def test_guest_and_logged_in_checkout_match_the_quote_despite_other_carts(self):
        good = self._plano_pair()
        self.assertEqual(Decimal(good['sub_total']), Decimal('44.95'))
        self.assertIsNone(good['lens_unavailable'])

        # Another shopper left a pair in the cart, then changed the
        # prescription to a power the sheet does not sell. The stored
        # sub_total is stale; the next pricing of that row refuses it.
        # Checkout of the plano pair must not see that row.
        other_rx = PrescriptionInfo.objects.create()
        other = CompleteSet.objects.create(
            frame=self.frame, lens_type=self.lens_type, function_path=self.function,
            index_option=self.index, prescription=other_rx)
        other_rx.sphere_r = Decimal('-8')
        other_rx.sphere_l = Decimal('-8')
        other_rx.save()
        self.assertIsNone(other.order_id)

        added = self.client.post('/api/order/guest_cart', {
            'action': 'add', 'complete_set_id': good['id'],
        }, format='json')
        self.assertEqual(added.status_code, 200, added.content)
        cart = self.client.post('/api/order/guest_cart', {'action': 'get'}, format='json')
        self.assertEqual(cart.status_code, 200, cart.content)
        self.assertEqual(Decimal(cart.data['active_subtotal']), Decimal('44.95'))
        self.assertEqual(cart.data['eyeglasses_set'][0]['sub_total'], '44.95')

        guest = self.client.post('/api/order/create_pending_guest', {
            'complete_set_ids': [good['id']],
            'email': 'guest@example.com',
            'address_data': self._guest_address(),
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
        }, format='json')
        self.assertEqual(guest.status_code, 201, guest.content)
        self.assertEqual(Decimal(guest.data['sub_total']), Decimal('44.95'))
        order = OrderInfo.objects.get(pk=guest.data['order_id'])
        self.assertEqual(
            list(order.completeset_set.values_list('id', flat=True)),
            [good['id']])
        other.refresh_from_db()
        self.assertIsNone(other.order_id)

        # Logged-in checkout of a second identical pair, poison set still present.
        user = User.objects.create_user(username='buyer@example.com', password='test-pass-123')
        user.refresh_from_db()
        logged_in = APIClient()
        logged_in.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        logged_in.force_login(user)
        second = self._plano_pair()
        user.shopping_cart.eyeglasses_set.add(second['id'])
        address = Address.objects.create(customer=user, **_address_fields())
        response = logged_in.post('/api/order/create_pending', {
            'complete_set_ids': [second['id']],
            'address_id': address.id,
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
            'email': '',
            'sub_total': '1.00',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(response.data['sub_total']), Decimal('44.95'))

    def test_checkout_still_refuses_a_power_the_sheet_does_not_sell(self):
        good = self._plano_pair()
        rx = PrescriptionInfo.objects.get(pk=CompleteSet.objects.get(pk=good['id']).prescription_id)
        rx.sphere_r = Decimal('-8')
        rx.sphere_l = Decimal('-8')
        rx.save()
        added = self.client.post('/api/order/guest_cart', {
            'action': 'add', 'complete_set_id': good['id'],
        }, format='json')
        self.assertEqual(added.status_code, 200, added.content)
        guest = self.client.post('/api/order/create_pending_guest', {
            'complete_set_ids': [good['id']],
            'email': 'guest@example.com',
            'address_data': self._guest_address(),
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
        }, format='json')
        self.assertEqual(guest.status_code, 400, guest.content)
        self.assertEqual(guest.data['error'], 'Not offered for this prescription')
        self.assertFalse(OrderInfo.objects.exists())

    def test_checkout_still_refuses_cylinder_above_6(self):
        rx = PrescriptionInfo.objects.create(
            sphere_r=Decimal('0'), sphere_l=Decimal('0'),
            cylinder_r=Decimal('-6.25'), cylinder_l=Decimal('0'))
        with self.assertRaises(LensNotOffered) as caught:
            CompleteSet.objects.create(
                frame=self.frame, lens_type=self.lens_type,
                function_path=self.function, index_option=self.index,
                prescription=rx)
        self.assertEqual(str(caught.exception), 'Max CYL is 6.00D')
