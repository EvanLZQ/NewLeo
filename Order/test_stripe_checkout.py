"""Stripe Checkout (second payment method). The Stripe API is never called:
the three API wrappers in Order/stripe_checkout.py are patched, and webhook
requests are signed locally with the test endpoint secret so the real
stripe.Webhook signature check runs."""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from General.models import Address, Coupon
from Order.models import CompleteSet, OrderInfo, OrderPayment, OrderUpdates
from Order.stripe_checkout import to_cents
from Order.tests import _address_fields, _frame

User = get_user_model()

WHSEC = 'whsec_test_local_only'
STRIPE_ON = dict(
    STRIPE_ENABLED=True,
    STRIPE_SECRET_KEY='sk_test_local_only',
    STRIPE_WEBHOOK_SECRET=WHSEC,
    STRIPE_RETURN_BASE_URL='https://shop.example',
    STRIPE_STATEMENT_DESCRIPTOR_SUFFIX='',
)
P = 'Order.stripe_checkout.'


def _sign(payload, secret=WHSEC, timestamp=None):
    timestamp = int(timestamp or time.time())
    mac = hmac.new(secret.encode(), f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()
    return f't={timestamp},v1={mac}'


def _session(order, *, amount=None, currency='usd', payment_status='paid',
             status='complete', session_id='cs_test_1', pi='pi_test_1'):
    return {
        'id': session_id,
        'object': 'checkout.session',
        'url': f'https://checkout.stripe.com/c/pay/{session_id}',
        'status': status,
        'payment_status': payment_status,
        'amount_total': to_cents(order.total_amount) if amount is None else amount,
        'currency': currency,
        'payment_intent': pi,
        'metadata': {'order_id': str(order.pk), 'order_number': order.order_number},
        'customer_details': {'email': 'payer@example.com'},
        'livemode': False,
    }


def _event(event_type, obj, event_id='evt_test_1'):
    return {'id': event_id, 'object': 'event', 'type': event_type, 'data': {'object': obj}}


class StripeBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='stripe@example.com', password='test-pass-123')
        self.user.refresh_from_db()
        self.client = APIClient()
        self.client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        self.client.force_login(self.user)
        self.address = Address.objects.create(customer=self.user, **_address_fields())

    def _pending(self, price='80.10', sku='QA-STRIPE-1', client=None, **extra):
        complete_set = CompleteSet.objects.create(frame=_frame(sku, Decimal(price)))
        self.user.shopping_cart.eyeglasses_set.add(complete_set)
        body = {
            'complete_set_ids': [complete_set.id], 'address_id': self.address.id,
            'shipping_method': 'Priority Shipping', 'country': 'United States', 'email': '',
        }
        body.update(extra)
        res = (client or self.client).post('/api/order/create_pending', body, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return OrderInfo.objects.get(pk=res.data['order_id']), res

    def _create_session(self, order, client=None, session=None, **body):
        session = session or _session(order, status='open', payment_status='unpaid')
        with mock.patch(P + 'stripe_create_session', return_value=session) as create:
            res = (client or self.client).post(
                '/api/order/stripe/create_session', {'order_id': order.pk, **body}, format='json')
        return res, create

    def _guest_with_session(self):
        guest = APIClient()
        guest.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        frame = _frame('QA-STRIPE-GUEST', Decimal('80.10'))
        created = guest.post('/api/order/createcompleteset', {
            'frame': {'sku': frame.sku}, 'sub_total': '1.00'}, format='json')
        guest.post('/api/order/guest_cart', {'action': 'add', 'complete_set_id': created.data['id']},
                   format='json')
        res = guest.post('/api/order/create_pending_guest', {
            'complete_set_ids': [created.data['id']], 'email': 'guest-stripe@example.com',
            'address_data': _address_fields(), 'shipping_method': 'Priority Shipping',
            'country': 'United States'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        order = OrderInfo.objects.get(pk=res.data['order_id'])
        other_guest = APIClient()
        other_guest.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        res2, _ = self._create_session(order, client=other_guest)
        self.assertEqual(res2.status_code, 404)
        res3, create = self._create_session(order, client=guest)
        self.assertEqual(res3.status_code, 200, res3.data)
        self.assertEqual(create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'], 9212)
        self.assertEqual(create.call_args.args[0]['customer_email'], 'guest-stripe@example.com')
        return guest, order

    def _webhook(self, event, secret=WHSEC, signature=None):
        payload = json.dumps(event)
        return self.client.generic(
            'POST', '/api/order/stripe/webhook', payload, content_type='application/json',
            HTTP_STRIPE_SIGNATURE=signature if signature is not None else _sign(payload, secret))


class StripeDisabledTests(StripeBase):
    """Flag off (the default): deploying the code changes nothing."""

    def test_endpoints_404_when_flag_off(self):
        order, _ = self._pending()
        with mock.patch(P + 'stripe_create_session') as create:
            res = self.client.post('/api/order/stripe/create_session', {'order_id': order.pk}, format='json')
        self.assertEqual(res.status_code, 404)
        create.assert_not_called()
        self.assertEqual(self.client.get('/api/order/stripe/session_status?session_id=cs_x').status_code, 404)
        self.assertEqual(self._webhook(_event('checkout.session.completed', _session(order))).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')

    @override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='')
    def test_flag_on_without_key_is_still_off(self):
        order, _ = self._pending()
        res, create = self._create_session(order)
        self.assertEqual(res.status_code, 404)
        create.assert_not_called()

    @override_settings(**{**STRIPE_ON, 'STRIPE_WEBHOOK_SECRET': ''})
    def test_webhook_off_without_secret(self):
        order, _ = self._pending()
        self.assertEqual(self._webhook(_event('checkout.session.completed', _session(order))).status_code, 404)

    def test_cancel_does_not_call_stripe_when_off(self):
        order, _ = self._pending()
        OrderInfo.objects.filter(pk=order.pk).update(stripe_checkout_session_id='cs_test_old')
        with mock.patch(P + 'stripe_expire_session') as expire, \
                self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(f'/api/order/cancel_pending/{order.pk}').status_code, 204)
        expire.assert_not_called()


@override_settings(**STRIPE_ON)
class CreateSessionTests(StripeBase):
    def test_amount_is_server_total_in_cents(self):
        order, res = self._pending('80.10')
        self.assertEqual(res.data['total_amount'], '92.12')  # 80.10 + free ship + 12.02 duty
        # Anything amount-like in the request is ignored.
        res, create = self._create_session(order, amount='1.00', total_amount='1.00', currency='jpy')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['url'], 'https://checkout.stripe.com/c/pay/cs_test_1')
        params = create.call_args.args[0]
        item = params['line_items'][0]
        self.assertEqual(item['quantity'], 1)
        self.assertEqual(item['price_data']['unit_amount'], 9212)
        self.assertEqual(item['price_data']['currency'], 'usd')
        self.assertEqual(params['mode'], 'payment')
        self.assertEqual(params['metadata'], {'order_id': str(order.pk), 'order_number': order.order_number})
        self.assertEqual(params['payment_intent_data']['metadata']['order_id'], str(order.pk))
        self.assertEqual(params['client_reference_id'], order.order_number)
        self.assertEqual(params['customer_email'], 'stripe@example.com')
        self.assertEqual(params['success_url'],
                         'https://shop.example/checkout/stripe/success?session_id={CHECKOUT_SESSION_ID}')
        self.assertEqual(params['cancel_url'],
                         f'https://shop.example/checkout/stripe/cancel?order_id={order.pk}')
        self.assertGreaterEqual(params['expires_at'] - int(time.time()), 30 * 60)
        self.assertNotIn('payment_method_types', params)  # Dashboard decides
        order.refresh_from_db()
        self.assertEqual(order.stripe_checkout_session_id, 'cs_test_1')
        self.assertEqual(order.payment_status, 'UNPAID')

    def test_coupon_shipping_and_duty_match_create_pending(self):
        # 15% off 8.95 shipping = 7.61; $40 is under the $59 free-shipping
        # line; US duty minimum $9 -> 56.61, same as the PayPal amount.
        Coupon.objects.create(code='SHIP15', online=True, shipping_discount_type='Percentage',
                              shipping_discount_amount=Decimal('15'))
        order, res = self._pending('40.00', 'QA-STRIPE-SHIP', coupon_code='SHIP15')
        self.assertEqual(res.data['total_amount'], '56.61')
        _, create = self._create_session(order)
        self.assertEqual(create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'], 5661)

    def test_frame_coupon_free_shipping_uses_post_discount_amount(self):
        # $68.95 frame - 50% = 34.48 (< $59) -> shipping is charged.
        Coupon.objects.create(code='FRAME50', online=True, frame_discount_type='Percentage',
                              frame_discount_amount=Decimal('50'))
        order, res = self._pending('68.95', 'QA-STRIPE-F50', coupon_code='FRAME50')
        expected = to_cents(Decimal(res.data['total_amount']))
        self.assertEqual(res.data['shipping_cost'], '8.95')
        _, create = self._create_session(order)
        self.assertEqual(create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'], expected)

    @override_settings(STRIPE_STATEMENT_DESCRIPTOR_SUFFIX='ELW ORDER')
    def test_statement_descriptor_suffix_from_env(self):
        order, _ = self._pending()
        _, create = self._create_session(order)
        self.assertEqual(create.call_args.args[0]['payment_intent_data']['statement_descriptor_suffix'],
                         'ELW ORDER')

    def test_other_customers_order_is_404(self):
        order, _ = self._pending()
        other = User.objects.create_user(username='other@example.com', password='test-pass-123')
        client = APIClient()
        client.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        client.force_login(other)
        res, create = self._create_session(order, client=client)
        self.assertEqual(res.status_code, 404)
        create.assert_not_called()
        anon = APIClient()
        anon.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        res, create = self._create_session(order, client=anon)
        self.assertEqual(res.status_code, 404)

    def test_paid_or_cancelled_order_refused(self):
        order, _ = self._pending()
        OrderInfo.objects.filter(pk=order.pk).update(payment_status='PAID')
        res, create = self._create_session(order)
        self.assertEqual(res.status_code, 400)
        order2, _ = self._pending(sku='QA-STRIPE-2')
        self.client.delete(f'/api/order/cancel_pending/{order2.pk}')
        res, create = self._create_session(order2)
        self.assertEqual(res.status_code, 400)
        create.assert_not_called()

    def test_stripe_error_is_502_and_order_untouched(self):
        order, _ = self._pending()
        with mock.patch(P + 'stripe_create_session', side_effect=RuntimeError('boom')):
            res = self.client.post('/api/order/stripe/create_session', {'order_id': order.pk}, format='json')
        self.assertEqual(res.status_code, 502)
        order.refresh_from_db()
        self.assertEqual(order.stripe_checkout_session_id, '')

    def test_new_session_expires_previous_one(self):
        order, _ = self._pending()
        self._create_session(order)
        second = _session(order, session_id='cs_test_2', status='open', payment_status='unpaid')
        with mock.patch(P + 'stripe_expire_session') as expire, \
                self.captureOnCommitCallbacks(execute=True):
            res, _ = self._create_session(order, session=second)
        self.assertEqual(res.status_code, 200)
        expire.assert_called_once_with('cs_test_1')

    def test_cancel_pending_expires_open_session(self):
        order, _ = self._pending()
        self._create_session(order)
        with mock.patch(P + 'stripe_expire_session') as expire, \
                self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(f'/api/order/cancel_pending/{order.pk}').status_code, 204)
        expire.assert_called_once_with('cs_test_1')

    def test_guest_session_owner_only(self):
        self._guest_with_session()


@override_settings(**STRIPE_ON)
class WebhookTests(StripeBase):
    def _paid_order(self, **kw):
        order, _ = self._pending(**kw)
        self._create_session(order)
        order.refresh_from_db()
        return order

    def test_completed_marks_paid_like_paypal(self):
        order = self._paid_order()
        mail.outbox.clear()
        res = self._webhook(_event('checkout.session.completed', _session(order)))
        self.assertEqual(res.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')
        self.assertEqual(order.payment_type, 'stripe')
        self.assertEqual(order.stripe_payment_intent_id, 'pi_test_1')
        self.assertEqual(order.order_status, 'PROCESSING')
        self.assertFalse(order.issue_order)
        payment = OrderPayment.objects.get(order=order)
        self.assertEqual(payment.payment_gateway, 'stripe')
        self.assertEqual(payment.transaction_id, 'pi_test_1')
        self.assertEqual(payment.gateway_transaction_id, 'cs_test_1')
        self.assertEqual(payment.transaction_amount, Decimal('92.12'))
        self.assertEqual(payment.currency, 'USD')
        self.assertEqual(payment.payer_email, 'payer@example.com')
        # Same as PayPal: ship-to address frozen, item out of the cart, e-mail sent.
        self.assertNotEqual(order.address_id, self.address.id)
        self.assertIsNone(order.address.customer_id)
        self.assertEqual(self.user.shopping_cart.eyeglasses_set.count(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_bad_signature_rejected(self):
        order = self._paid_order()
        event = _event('checkout.session.completed', _session(order))
        self.assertEqual(self._webhook(event, secret='whsec_wrong').status_code, 400)
        self.assertEqual(self._webhook(event, signature='').status_code, 400)
        self.assertEqual(self._webhook(event, signature='t=1,v1=deadbeef').status_code, 400)
        # Correct secret but 10 minutes old (replay) — Stripe's 5 min tolerance.
        payload = json.dumps(event)
        old = _sign(payload, timestamp=time.time() - 600)
        res = self.client.generic('POST', '/api/order/stripe/webhook', payload,
                                  content_type='application/json', HTTP_STRIPE_SIGNATURE=old)
        self.assertEqual(res.status_code, 400)
        # Payload changed after signing.
        tampered = json.dumps(_event('checkout.session.completed', _session(order, amount=1)))
        res = self.client.generic('POST', '/api/order/stripe/webhook', tampered,
                                  content_type='application/json', HTTP_STRIPE_SIGNATURE=_sign(payload))
        self.assertEqual(res.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self.assertFalse(OrderPayment.objects.filter(order=order).exists())

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get('/api/order/stripe/webhook').status_code, 405)

    def test_idempotent_on_retries_and_both_paths(self):
        order = self._paid_order()
        mail.outbox.clear()
        event = _event('checkout.session.completed', _session(order))
        for _ in range(3):
            self.assertEqual(self._webhook(event).status_code, 200)
        # payment_intent.succeeded for the same payment.
        pi = {'id': 'pi_test_1', 'object': 'payment_intent', 'amount': 9212, 'amount_received': 9212,
              'currency': 'usd', 'metadata': {'order_id': str(order.pk)}}
        self.assertEqual(self._webhook(_event('payment_intent.succeeded', pi, 'evt_2')).status_code, 200)
        # The success page checking after the webhook.
        with mock.patch(P + 'stripe_retrieve_session', return_value=_session(order)):
            res = self.client.get('/api/order/stripe/session_status?session_id=cs_test_1')
        self.assertEqual(res.data['status'], 'paid')
        self.assertEqual(OrderPayment.objects.filter(order=order).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_amount_mismatch_rejected_and_flagged(self):
        order = self._paid_order()
        res = self._webhook(_event('checkout.session.completed', _session(order, amount=100)))
        self.assertEqual(res.status_code, 200)  # handled; no point in Stripe retrying
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self.assertTrue(order.issue_order)
        self.assertFalse(OrderPayment.objects.filter(order=order).exists())
        self.assertTrue(OrderUpdates.objects.filter(order=order, title__contains='mismatch').exists())

    def test_currency_mismatch_rejected(self):
        order = self._paid_order()
        for currency in ('eur', 'cad', 'jpy', ''):
            self._webhook(_event('checkout.session.completed', _session(order, currency=currency)))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self.assertFalse(OrderPayment.objects.filter(order=order).exists())
        self.assertEqual(OrderUpdates.objects.filter(order=order).count(), 4)

    def test_unpaid_completed_session_waits_for_async_success(self):
        order = self._paid_order()
        self._webhook(_event('checkout.session.completed', _session(order, payment_status='unpaid')))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self._webhook(_event('checkout.session.async_payment_failed',
                             _session(order, payment_status='unpaid'), 'evt_f'))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self._webhook(_event('checkout.session.async_payment_succeeded', _session(order), 'evt_2'))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')

    def test_payment_intent_succeeded_alone_marks_paid(self):
        order = self._paid_order()
        pi = {'id': 'pi_only', 'object': 'payment_intent', 'amount': 9212, 'amount_received': 9212,
              'currency': 'usd', 'metadata': {'order_id': str(order.pk)}}
        self._webhook(_event('payment_intent.succeeded', pi))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')
        self.assertEqual(order.stripe_payment_intent_id, 'pi_only')
        # Not ours (no order metadata) -> ignored.
        self.assertEqual(self._webhook(_event('payment_intent.succeeded', {
            'id': 'pi_other', 'amount_received': 500, 'currency': 'usd', 'metadata': {}}, 'e3')).status_code, 200)

    def test_payment_failed_leaves_order_unpaid(self):
        order = self._paid_order()
        pi = {'id': 'pi_fail', 'metadata': {'order_id': str(order.pk)},
              'last_payment_error': {'message': 'Your card was declined.'}}
        self.assertEqual(self._webhook(_event('payment_intent.payment_failed', pi)).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')
        self.assertTrue(OrderUpdates.objects.filter(order=order, details__contains='declined').exists())

    def test_order_paid_by_paypal_then_stripe_is_flagged(self):
        order = self._paid_order()
        OrderInfo.objects.filter(pk=order.pk).update(payment_status='PAID', payment_type='paypal')
        self._webhook(_event('checkout.session.completed', _session(order)))
        order.refresh_from_db()
        self.assertEqual(order.payment_type, 'paypal')
        self.assertTrue(order.issue_order)
        self.assertFalse(OrderPayment.objects.filter(order=order, payment_gateway='stripe').exists())

    def test_paid_after_cancel_is_recorded_and_flagged(self):
        order = self._paid_order()
        self.client.delete(f'/api/order/cancel_pending/{order.pk}')
        mail.outbox.clear()
        self._webhook(_event('checkout.session.completed', _session(order)))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')
        self.assertTrue(order.issue_order)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(OrderUpdates.objects.filter(order=order, title__contains='after cancel').exists())

    def test_refund_recorded_without_touching_order_status(self):
        order = self._paid_order()
        self._webhook(_event('checkout.session.completed', _session(order)))
        charge = {'id': 'ch_1', 'object': 'charge', 'payment_intent': 'pi_test_1', 'amount': 9212,
                  'amount_refunded': 2000, 'refunded': False, 'currency': 'usd', 'metadata': {}}
        self._webhook(_event('charge.refunded', charge, 'evt_r1'))
        order.refresh_from_db()
        self.assertEqual(order.refound_status, 'partially_refunded')
        self.assertEqual(order.refound_amount, Decimal('20.00'))
        charge.update(amount_refunded=9212, refunded=True)
        for _ in range(2):
            self._webhook(_event('charge.refunded', charge, 'evt_r2'))
        order.refresh_from_db()
        self.assertEqual(order.refound_status, 'refunded')
        self.assertEqual(order.refound_amount, Decimal('92.12'))
        self.assertEqual(order.order_status, 'PROCESSING')
        self.assertEqual(order.payment_status, 'PAID')
        self.assertEqual(OrderUpdates.objects.filter(order=order, title='Stripe: refund').count(), 2)

    def test_unknown_order_and_unhandled_events_are_200(self):
        order = self._paid_order()
        session = _session(order)
        session['metadata'] = {'order_id': '999999'}
        self.assertEqual(self._webhook(_event('checkout.session.completed', session)).status_code, 200)
        self.assertEqual(self._webhook(_event('customer.created', {'id': 'cus_1'})).status_code, 200)

    def test_handler_crash_is_500_so_stripe_retries(self):
        order = self._paid_order()
        with mock.patch(P + '_fulfil', side_effect=RuntimeError('db down')):
            res = self._webhook(_event('checkout.session.completed', _session(order)))
        self.assertEqual(res.status_code, 500)


@override_settings(**STRIPE_ON)
class SessionStatusTests(StripeBase):
    def test_paid_session_marks_order_paid(self):
        order, _ = self._pending()
        self._create_session(order)
        with mock.patch(P + 'stripe_retrieve_session', return_value=_session(order)) as retrieve:
            res = self.client.get('/api/order/stripe/session_status?session_id=cs_test_1')
        retrieve.assert_called_once_with('cs_test_1')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, {'status': 'paid', 'order_number': order.order_number,
                                    'total_amount': '92.12', 'shipping_cost': '0.00'})
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')

    def test_open_and_expired(self):
        order, _ = self._pending()
        self._create_session(order)
        for stripe_status, expected in (('open', 'open'), ('expired', 'expired')):
            with mock.patch(P + 'stripe_retrieve_session', return_value=_session(
                    order, status=stripe_status, payment_status='unpaid')):
                res = self.client.get('/api/order/stripe/session_status?session_id=cs_test_1')
            self.assertEqual(res.data['status'], expected)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')

    def test_mismatch_reports_error(self):
        order, _ = self._pending()
        self._create_session(order)
        with mock.patch(P + 'stripe_retrieve_session', return_value=_session(order, amount=1)):
            res = self.client.get('/api/order/stripe/session_status?session_id=cs_test_1')
        self.assertEqual(res.data['status'], 'error')
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'UNPAID')

    def test_not_owner_is_404(self):
        order, _ = self._pending()
        self._create_session(order)
        anon = APIClient()
        anon.defaults['HTTP_X_FORWARDED_PROTO'] = 'https'
        with mock.patch(P + 'stripe_retrieve_session', return_value=_session(order)) as retrieve:
            res = anon.get('/api/order/stripe/session_status?session_id=cs_test_1')
            self.assertEqual(res.status_code, 404)
            res = self.client.get('/api/order/stripe/session_status?session_id=cs_unknown')
            self.assertEqual(res.status_code, 404)
            res = self.client.get('/api/order/stripe/session_status')
            self.assertEqual(res.status_code, 400)
        retrieve.assert_not_called()

    def test_guest_flow_end_to_end(self):
        guest, order = self._guest_with_session()
        with mock.patch(P + 'stripe_retrieve_session', return_value=_session(order)):
            res = guest.get('/api/order/stripe/session_status?session_id=cs_test_1')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['status'], 'paid')
            self.assertEqual(res.data['email'], 'guest-stripe@example.com')
            # Reload of the success page still works (session popped the pending id).
            res = guest.get('/api/order/stripe/session_status?session_id=cs_test_1')
            self.assertEqual(res.data['status'], 'paid')
        self.assertEqual(guest.session['guest_completed_order']['order_number'], order.order_number)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'PAID')
        self.assertEqual(OrderPayment.objects.filter(order=order).count(), 1)
