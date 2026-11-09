from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from General.models import Address
from Order.models import CompleteSet, OrderInfo
from Order.serializer import OrderSerializer
from Order.service.order_service import OrderService
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
