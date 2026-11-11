from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Customer.models import PasswordResetCode, ShoppingCart
from Order.models import CompleteSet, OrderInfo
from Product.models import ProductInfo, ProductInstance

User = get_user_model()

LOCMEM_EMAIL = override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')

GOOD_PASSWORD = 'Shop-Test-2026-qa'


def _frame(sku='QA-CUST-1', price='35.00'):
    product = ProductInfo.objects.create(
        model_number=sku, price=Decimal(price), letter_size='M',
        string_size='52-18-145', frame_weight=20, frame_width=140, lens_width=52,
        bridge=18, temple_length=145, lens_height=40, upper_wearable_width=130,
        lower_wearable_width=125, nose_pad='Standard', frame_style='Full-Rim',
    )
    return ProductInstance.objects.create(
        product=product, sku=sku, price=Decimal(price),
        color_base_name='black', color_display_name='Black', online=True,
    )


@LOCMEM_EMAIL
class SignUpTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _signup(self, username, password=GOOD_PASSWORD):
        return self.client.post('/api/user/create_user',
                                {'username': username, 'password': password}, format='json')

    def test_signup_creates_account_and_signs_in(self):
        # Several AUTHENTICATION_BACKENDS are configured; login() used to
        # raise here, so the account was created but the customer got a 500.
        res = self._signup('New.Customer@Example.com')
        self.assertEqual(res.status_code, 201, res.content)
        user = User.objects.get()
        self.assertEqual(user.username, 'new.customer@example.com')
        self.assertEqual(user.email, 'new.customer@example.com')
        self.assertEqual(self.client.get('/api/user/summary').status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # welcome email

    def test_weak_password_is_rejected(self):
        res = self._signup('weak@example.com', '12345')
        self.assertEqual(res.status_code, 400)
        self.assertIn('password', res.data)
        self.assertFalse(User.objects.exists())

    def test_invalid_email_is_rejected(self):
        res = self._signup('not-an-email')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_is_case_insensitive(self):
        User.objects.create_user(username='Taken@Example.com', password=GOOD_PASSWORD)
        res = self._signup('taken@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(User.objects.count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        User.objects.create_user(username='shopper@example.com', password=GOOD_PASSWORD)

    def _login(self, username, password=GOOD_PASSWORD):
        return self.client.post('/api/user/login',
                                {'username': username, 'password': password}, format='json')

    def test_login_ignores_email_case_and_spaces(self):
        res = self._login('  Shopper@Example.COM ')
        self.assertEqual(res.status_code, 200, res.content)

    def test_successful_logins_are_not_rate_limited(self):
        for _ in range(12):
            self.assertEqual(self._login('shopper@example.com').status_code, 200)
            self.client.post('/api/user/logout')

    def test_repeated_failures_are_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self._login('shopper@example.com', 'wrong').status_code, 400)
        self.assertEqual(self._login('shopper@example.com').status_code, 429)

    def test_rate_limit_response_is_not_shared(self):
        from Customer import views
        self.assertIsNot(views._rate_limit_response(), views._rate_limit_response())


@LOCMEM_EMAIL
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        # Mixed-case username, as older accounts may have.
        self.user = User.objects.create_user(username='Reset.Me@Example.com',
                                             password='Old-Pass-2026-qa')

    def _code_from_email(self):
        import re
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)

    def test_full_reset_flow(self):
        res = self.client.post('/api/user/forgot-password/request-code',
                               {'email': 'reset.me@example.com'}, format='json')
        self.assertEqual(res.status_code, 200)
        code = self._code_from_email()

        res = self.client.post('/api/user/forgot-password/verify-code',
                               {'email': 'reset.me@example.com', 'code': code}, format='json')
        self.assertEqual(res.status_code, 200, res.content)

        res = self.client.post('/api/user/forgot-password/reset', {
            'email': 'reset.me@example.com', 'code': code,
            'new_password': GOOD_PASSWORD, 'confirm_password': GOOD_PASSWORD,
        }, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(GOOD_PASSWORD))
        self.assertFalse(PasswordResetCode.objects.filter(used=False).exists())

        # A used code cannot be replayed.
        res = self.client.post('/api/user/forgot-password/reset', {
            'email': 'reset.me@example.com', 'code': code,
            'new_password': 'Another-Pass-2026', 'confirm_password': 'Another-Pass-2026',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_unknown_email_gets_generic_answer_and_no_mail(self):
        res = self.client.post('/api/user/forgot-password/request-code',
                               {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_is_rejected(self):
        self.client.post('/api/user/forgot-password/request-code',
                         {'email': 'reset.me@example.com'}, format='json')
        code = self._code_from_email()
        wrong = '000000' if code != '000000' else '111111'
        res = self.client.post('/api/user/forgot-password/reset', {
            'email': 'reset.me@example.com', 'code': wrong,
            'new_password': GOOD_PASSWORD, 'confirm_password': GOOD_PASSWORD,
        }, format='json')
        self.assertEqual(res.status_code, 400)


class GuestCartMergeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.frame = _frame()

    def _guest_add(self):
        # Created through the API in this guest session, as the storefront
        # does: an item with no recorded owner can no longer be claimed by id
        # (2026-11-11 cart-enumeration fix).
        res = self.client.post('/api/order/createcompleteset',
                               {'frame': {'sku': self.frame.sku}}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        complete_set = CompleteSet.objects.get(id=res.data['id'])
        res = self.client.post('/api/order/guest_cart',
                               {'action': 'add', 'complete_set_id': complete_set.id}, format='json')
        self.assertEqual(res.status_code, 200)
        return complete_set

    def test_first_login_on_a_new_device_keeps_guest_items(self):
        # The storefront calls create_shopping_cart when the browser has no
        # saved cart id; that path used to skip the guest-cart merge.
        complete_set = self._guest_add()
        user = User.objects.create_user(username='merge@example.com', password=GOOD_PASSWORD)
        self.client.post('/api/user/login',
                         {'username': 'merge@example.com', 'password': GOOD_PASSWORD}, format='json')

        res = self.client.post('/api/user/create_shopping_cart', {}, format='json')
        self.assertIn(res.status_code, (200, 201))
        ids = [item['id'] for item in res.data['eyeglasses_set']]
        self.assertEqual(ids, [complete_set.id])
        user.refresh_from_db()
        self.assertTrue(user.shopping_cart.eyeglasses_set.filter(id=complete_set.id).exists())

    def test_signup_from_guest_session_keeps_items(self):
        complete_set = self._guest_add()
        self.client.post('/api/user/create_user',
                         {'username': 'fresh@example.com', 'password': GOOD_PASSWORD}, format='json')
        res = self.client.post('/api/user/create_shopping_cart', {}, format='json')
        self.assertEqual([i['id'] for i in res.data['eyeglasses_set']], [complete_set.id])


class CustomerOrderListTests(TestCase):
    def test_unpaid_checkout_attempts_are_not_listed(self):
        user = User.objects.create_user(username='orders@example.com', password=GOOD_PASSWORD)
        common = dict(customer=user, email=user.username, sub_total=0, shipping_cost=0,
                      total_amount=0, refound_amount=0, order_status='PROCESSING')
        OrderInfo.objects.create(order_number='ELW-T-PAID', payment_status='PAID', **common)
        OrderInfo.objects.create(order_number='ELW-T-UNPAID', payment_status='UNPAID', **common)
        client = APIClient()
        client.force_login(user)
        res = client.get('/api/user/get_customer_order')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([o['order_number'] for o in res.data], ['ELW-T-PAID'])
