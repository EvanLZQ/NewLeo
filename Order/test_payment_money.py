"""PayPal money correctness.

1. Every stored/returned amount is rounded to the cent, half up, so the
   amount the browser sends to PayPal (parseFloat(total_amount).toFixed(2))
   is the stored order.total_amount. Before: sub_total 80.10 (US) returned
   total_amount "92.1150"; the browser charged 92.11, the DB held 92.12, and
   confirm_payment refused a payment the customer had already made.
2. confirm_payment refuses a capture in another currency, even when the
   number matches.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from General.models import Address, Coupon
from Order.models import CompleteSet, OrderInfo, OrderPayment
from Order.service.order_service import OrderService, money
from Order.tests import _address_fields, _frame
from Order.views import _verify_and_extract_capture

User = get_user_model()


def _paypal_order(value, currency='USD', capture_id='CAP-1'):
    return {
        'status': 'COMPLETED',
        'payer': {'email_address': 'payer@example.com'},
        'purchase_units': [{'payments': {'captures': [{
            'id': capture_id,
            'amount': {'value': value, 'currency_code': currency},
        }]}}],
    }


def _browser_amount(total_amount):
    """What PaymentForm.tsx does: parseFloat(x).toFixed(2).

    Python's float formatting matches JS toFixed for these values (both
    round the binary double, e.g. 92.1150 -> 92.11)."""
    return '%.2f' % float(total_amount)


class MoneyHelperTests(TestCase):
    def test_half_cent_rounds_up(self):
        self.assertEqual(str(money(Decimal('12.015'))), '12.02')
        self.assertEqual(str(money(Decimal('92.1150'))), '92.12')
        self.assertEqual(str(money(0)), '0.00')
        self.assertEqual(str(money(8.95)), '8.95')

    def test_customs_fee_is_whole_cents(self):
        # 15% of 80.10 is 12.015. Same as helper.ts previewCustomsFee (12.02).
        self.assertEqual(
            str(OrderService.calculate_customs_fee('United States', Decimal('80.10'))),
            '12.02')
        self.assertEqual(
            str(OrderService.calculate_customs_fee('United States', Decimal('40'))),
            '9.00')


class RoundedPendingOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='money@example.com', password='test-pass-123')
        self.user.refresh_from_db()
        self.client = APIClient()
        self.client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        self.client.force_login(self.user)
        self.address = Address.objects.create(customer=self.user, **_address_fields())

    def _set(self, price, sku):
        complete_set = CompleteSet.objects.create(frame=_frame(sku, Decimal(price)))
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        return complete_set

    def _create_pending(self, complete_set, **extra):
        body = {
            'complete_set_ids': [complete_set.id],
            'address_id': self.address.id,
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
            'email': '',
        }
        body.update(extra)
        res = self.client.post('/api/order/create_pending', body, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return res

    def _assert_browser_matches_db(self, res):
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        for field in ('sub_total', 'shipping_cost', 'customs_fee', 'total_amount'):
            self.assertEqual(Decimal(res.data[field]), getattr(order, field), field)
            # Exactly two decimals, no sub-cent digits.
            self.assertRegex(res.data[field], r'^\d+\.\d{2}$', field)
        self.assertEqual(_browser_amount(res.data['total_amount']), str(order.total_amount))
        return order

    def test_us_80_10_total_is_92_12_everywhere(self):
        res = self._create_pending(self._set('80.10', 'QA-MONEY-8010'))
        # 80.10 >= $59 and one pair: Priority Shipping is free.
        self.assertEqual(res.data['sub_total'], '80.10')
        self.assertEqual(res.data['shipping_cost'], '0.00')
        self.assertEqual(res.data['customs_fee'], '12.02')
        self.assertEqual(res.data['total_amount'], '92.12')
        order = self._assert_browser_matches_db(res)
        self.assertEqual(order.total_amount, Decimal('92.12'))

    def test_us_80_10_paypal_charge_of_92_12_confirms(self):
        res = self._create_pending(self._set('80.10', 'QA-MONEY-8010B'))
        charged = _browser_amount(res.data['total_amount'])
        self.assertEqual(charged, '92.12')
        with mock.patch('Order.views._fetch_paypal_order',
                        return_value=_paypal_order(charged)):
            confirm = self.client.post('/api/order/confirm_payment', {
                'order_id': res.data['order_id'], 'paypal_order_id': 'PP-8010',
            }, format='json')
        self.assertEqual(confirm.status_code, 200, confirm.data)
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.payment_status, 'PAID')

    def test_percentage_coupon_leaves_no_sub_cent(self):
        # 10% of a 80.15 frame is 8.015. Before: sub_total 72.135,
        # customs 10.82025, total "82.95525" returned to the browser.
        Coupon.objects.create(
            code='TENFRAME', online=True,
            frame_discount_type='Percentage', frame_discount_amount=Decimal('10'))
        res = self._create_pending(self._set('80.15', 'QA-MONEY-8015'),
                                   coupon_code='TENFRAME')
        self.assertEqual(res.data['sub_total'], '72.13')
        self.assertEqual(res.data['shipping_cost'], '0.00')
        self.assertEqual(res.data['customs_fee'], '10.82')
        self.assertEqual(res.data['total_amount'], '82.95')
        self.assertEqual(res.data['discount_amount'], '8.02')
        self._assert_browser_matches_db(res)

    def test_percentage_shipping_coupon_is_whole_cents(self):
        # 15% off 8.95 shipping is 1.3425. Sub_total 40 stays under $59.
        Coupon.objects.create(
            code='SHIP15', online=True,
            shipping_discount_type='Percentage', shipping_discount_amount=Decimal('15'))
        res = self._create_pending(self._set('40.00', 'QA-MONEY-SHIP'),
                                   coupon_code='SHIP15')
        self.assertEqual(res.data['shipping_cost'], '7.61')  # 8.95 - 1.34
        self.assertEqual(res.data['customs_fee'], '9.00')
        self.assertEqual(res.data['total_amount'], '56.61')
        self._assert_browser_matches_db(res)

    def test_update_order_totals_rounds_too(self):
        # OrderInfo.save() path (admin / order edits).
        complete_set = self._set('80.10', 'QA-MONEY-SAVE')
        order = OrderInfo.objects.create(
            customer=self.user, email=self.user.username, address=self.address,
            order_number='ELW-MONEY-SAVE', shipping_company='Priority Shipping',
            payment_status='UNPAID', payment_type='paypal', comment='',
            refound_status='', refound_amount=0,
            sub_total=0, shipping_cost=0, total_amount=0)
        CompleteSet.objects.filter(pk=complete_set.pk).update(order=order)
        order.refresh_from_db()
        OrderService.update_order_totals(order)
        self.assertEqual(str(order.customs_fee), '12.02')
        self.assertEqual(str(order.total_amount), '92.12')


class GuestRoundedPendingOrderTests(TestCase):
    def test_guest_80_10_total_is_92_12(self):
        client = APIClient()
        client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        frame = _frame('QA-MONEY-GUEST', Decimal('80.10'))
        created = client.post('/api/order/createcompleteset', {
            'frame': {'sku': frame.sku}, 'sub_total': '1.00',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        added = client.post('/api/order/guest_cart', {
            'action': 'add', 'complete_set_id': created.data['id'],
        }, format='json')
        self.assertEqual(added.status_code, 200, added.content)
        res = client.post('/api/order/create_pending_guest', {
            'complete_set_ids': [created.data['id']],
            'email': 'guest-money@example.com',
            'address_data': _address_fields(),
            'shipping_method': 'Priority Shipping',
            'country': 'United States',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data['sub_total'], '80.10')
        self.assertEqual(res.data['customs_fee'], '12.02')
        self.assertEqual(res.data['total_amount'], '92.12')
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.total_amount, Decimal('92.12'))
        self.assertEqual(_browser_amount(res.data['total_amount']), '92.12')


class CaptureCurrencyTests(TestCase):
    def _verify(self, paypal_order, total='92.12'):
        with mock.patch('Order.views._fetch_paypal_order', return_value=paypal_order):
            return _verify_and_extract_capture('PP-X', Decimal(total))

    def test_usd_capture_passes(self):
        capture_id, amount, email = self._verify(_paypal_order('92.12', 'USD'))
        self.assertEqual(capture_id, 'CAP-1')
        self.assertEqual(amount, Decimal('92.12'))
        self.assertEqual(email, 'payer@example.com')

    def test_same_number_in_another_currency_is_refused(self):
        for currency in ('JPY', 'MXN', 'CAD', 'usd'):
            capture_id, amount, error = self._verify(_paypal_order('92.12', currency))
            self.assertIsNone(capture_id, currency)
            self.assertIsNone(amount, currency)
            self.assertEqual(
                error, 'Captured currency does not match the order currency', currency)

    def test_missing_currency_is_refused(self):
        paypal_order = _paypal_order('92.12')
        del paypal_order['purchase_units'][0]['payments']['captures'][0]['amount']['currency_code']
        capture_id, _, error = self._verify(paypal_order)
        self.assertIsNone(capture_id)
        self.assertEqual(error, 'Unexpected PayPal response shape')

    def test_confirm_payment_in_jpy_leaves_order_unpaid(self):
        user = User.objects.create_user(username='jpy@example.com', password='test-pass-123')
        user.refresh_from_db()
        client = APIClient()
        client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        client.force_login(user)
        address = Address.objects.create(customer=user, **_address_fields())
        complete_set = CompleteSet.objects.create(frame=_frame('QA-MONEY-JPY', Decimal('80.10')))
        user.shopping_cart.eyeglasses_set.add(complete_set)
        res = client.post('/api/order/create_pending', {
            'complete_set_ids': [complete_set.id], 'address_id': address.id,
            'shipping_method': 'Priority Shipping', 'country': 'United States', 'email': '',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        with mock.patch('Order.views._fetch_paypal_order',
                        return_value=_paypal_order(res.data['total_amount'], 'JPY')):
            confirm = client.post('/api/order/confirm_payment', {
                'order_id': res.data['order_id'], 'paypal_order_id': 'PP-JPY',
            }, format='json')
        self.assertEqual(confirm.status_code, 400, confirm.data)
        self.assertEqual(confirm.data['error'],
                         'Captured currency does not match the order currency')
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.payment_status, 'UNPAID')
        self.assertFalse(OrderPayment.objects.filter(order=order).exists())

    def test_confirm_payment_guest_in_jpy_is_refused(self):
        client = APIClient()
        client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        frame = _frame('QA-MONEY-GJPY', Decimal('80.10'))
        created = client.post('/api/order/createcompleteset', {
            'frame': {'sku': frame.sku}, 'sub_total': '1.00'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        client.post('/api/order/guest_cart', {
            'action': 'add', 'complete_set_id': created.data['id']}, format='json')
        res = client.post('/api/order/create_pending_guest', {
            'complete_set_ids': [created.data['id']], 'email': 'gjpy@example.com',
            'address_data': _address_fields(), 'shipping_method': 'Priority Shipping',
            'country': 'United States',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        with mock.patch('Order.views._fetch_paypal_order',
                        return_value=_paypal_order(res.data['total_amount'], 'JPY')):
            confirm = client.post('/api/order/confirm_payment_guest', {
                'order_id': res.data['order_id'], 'paypal_order_id': 'PP-GJPY',
                'email': 'gjpy@example.com',
            }, format='json')
        self.assertEqual(confirm.status_code, 400, confirm.content)
        self.assertEqual(confirm.data['error'],
                         'Captured currency does not match the order currency')
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        self.assertEqual(order.payment_status, 'UNPAID')
