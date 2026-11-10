import importlib

from django.apps import apps
from django.test import TestCase

from General.models import FAQ

_faq_migration = importlib.import_module('General.migrations.0013_seed_launch_faqs')
LAUNCH_FAQS = _faq_migration.LAUNCH_FAQS
seed_launch_faqs = _faq_migration.seed_launch_faqs


class LaunchFAQTests(TestCase):
    def test_seed_is_idempotent_and_matches_policy(self):
        titles = [title for _order, title, _content in LAUNCH_FAQS]
        self.assertEqual(
            list(FAQ.objects.filter(title__in=titles).values_list('title', flat=True)),
            titles,
        )

        by_title = {row.title: row.content for row in FAQ.objects.filter(title__in=titles)}
        shipping = by_title["How much is shipping?"]
        delivery = by_title["How long does delivery take?"]
        self.assertIn("Canada and the United States only", by_title["Where do you ship?"])
        self.assertIn("$59.00", shipping)
        self.assertIn("fewer than 3 pairs", shipping)
        self.assertIn("$8.95", shipping)
        self.assertIn("$24.95", shipping)
        self.assertIn("Canada only", shipping)
        self.assertIn("United States ship by Priority Shipping", shipping)
        self.assertIn("7–15", delivery)
        self.assertIn("5–10", delivery)
        self.assertIn("3–7", delivery)
        self.assertIn("6.00D", by_title["What is the maximum cylinder (CYL)?"])
        customs = by_title["Do US orders have a customs or import fee?"]
        self.assertIn("15%", customs)
        self.assertIn("$9.00", customs)
        self.assertIn("Canada do not include this fee", customs)
        payment = by_title["How can I pay?"]
        self.assertIn("PayPal", payment)
        self.assertIn("Pay Later", payment)
        self.assertIn("debit or credit card", payment)
        blob = "\n".join(by_title.values()).lower()
        self.assertNotIn("worldwide", blob)
        self.assertNotIn("virtual try-on", blob)
        self.assertNotIn("warranty", blob)

        seed_launch_faqs(apps, None)
        self.assertEqual(FAQ.objects.filter(title__in=titles).count(), len(titles))

        edited = FAQ.objects.get(title="Where do you ship?")
        edited.content = "Edited by staff."
        edited.save(update_fields=['content'])
        seed_launch_faqs(apps, None)
        edited.refresh_from_db()
        self.assertEqual(edited.content, "Edited by staff.")
        self.assertEqual(FAQ.objects.filter(title="Where do you ship?").count(), 1)

        FAQ.objects.filter(title="How can I pay?").delete()
        seed_launch_faqs(apps, None)
        self.assertEqual(
            FAQ.objects.get(title="How can I pay?").content,
            dict((title, content) for _order, title, content in LAUNCH_FAQS)["How can I pay?"],
        )

        response = self.client.get('/api/general/faq')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['title'] for row in response.json()], titles)


class ContactFormTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_message_is_stored_for_staff(self):
        from rest_framework.test import APIClient
        from Customer.models import CustomerMessage
        res = APIClient().post('/api/general/contact', {
            'name': 'QA', 'email': 'QA@Example.com', 'order_number': 'ELW-1',
            'message': 'Where is my order?',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        msg = CustomerMessage.objects.get()
        self.assertIsNone(msg.customer)
        self.assertIn('qa@example.com', msg.content)
        self.assertIn('ELW-1', msg.content)
        self.assertIn('Where is my order?', msg.content)

    def test_requires_valid_email_and_message(self):
        from rest_framework.test import APIClient
        client = APIClient()
        self.assertEqual(client.post('/api/general/contact',
                                     {'email': 'nope', 'message': 'hi'}, format='json').status_code, 400)
        self.assertEqual(client.post('/api/general/contact',
                                     {'email': 'a@example.com', 'message': ''}, format='json').status_code, 400)

    def test_rate_limited_per_ip(self):
        from rest_framework.test import APIClient
        client = APIClient()
        body = {'email': 'a@example.com', 'message': 'hi'}
        for _ in range(5):
            self.assertEqual(client.post('/api/general/contact', body, format='json').status_code, 201)
        self.assertEqual(client.post('/api/general/contact', body, format='json').status_code, 429)


class ProductSearchFilterTests(TestCase):
    def test_search_sent_as_list_matches(self):
        import json
        from decimal import Decimal
        from rest_framework.test import APIClient
        from Product.models import ProductInfo, ProductInstance
        product = ProductInfo.objects.create(
            model_number='63027', name='Cosima', price=Decimal('35'), letter_size='M',
            string_size='50-18-140', frame_weight=15, frame_width=133, lens_width=50,
            bridge=18, temple_length=140, lens_height=42, upper_wearable_width=133,
            lower_wearable_width=137, nose_pad='Adjustable', frame_style='Full-Rim')
        ProductInstance.objects.create(product=product, sku='QA-SRCH-1', price=Decimal('35'),
                                       color_base_name='red', color_display_name='Red', online=True)
        client = APIClient()
        for search in (['cos'], 'cos', ['COSIMA']):
            res = client.get('/api/products/filter', {'filter': json.dumps({'Search': search})})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['total_count'], 1, search)
        res = client.get('/api/products/filter', {'filter': json.dumps({'Search': ['zzz']})})
        self.assertEqual(res.data['total_count'], 0)
