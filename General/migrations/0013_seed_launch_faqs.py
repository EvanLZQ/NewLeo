# Launch FAQ copy for GET /api/general/faq. Production was returning []
# ("No questions yet") because nothing had ever inserted FAQ rows.
# get_or_create on title so a re-run does not duplicate, and so an edited
# answer is left alone.

from django.db import migrations


# (sort_order, title, content). Policy text matches the live checkout rules
# in Order/service/order_service.py and the storefront shipping copy:
# Canada and the US only, Priority free at $59.00 with fewer than 3 pairs
# otherwise $8.95, UPS $24.95 Canada only, delivery windows plus lens
# processing, max CYL 6.00D, US customs 15% / $9 minimum, PayPal checkout.
LAUNCH_FAQS = [
    (
        10,
        "Where do you ship?",
        "We ship to Canada and the United States only.",
    ),
    (
        20,
        "How much is shipping?",
        "Priority Shipping is free on orders of $59.00 or more with fewer than "
        "3 pairs of glasses. Otherwise Priority Shipping is $8.95.\n\n"
        "UPS is $24.95 and is available for addresses in Canada only. "
        "Orders to the United States ship by Priority Shipping.",
    ),
    (
        30,
        "How long does delivery take?",
        "Priority Shipping usually takes 7–15 business days. UPS, which is "
        "available in Canada only, usually takes 5–10 business days.\n\n"
        "Those estimates do not include lens processing, which usually adds "
        "about 3–7 business days.",
    ),
    (
        40,
        "What is the maximum cylinder (CYL)?",
        "The maximum cylinder (CYL) we can make is 6.00D.",
    ),
    (
        50,
        "Do US orders have a customs or import fee?",
        "Orders shipped to the United States include a customs and import fee "
        "of 15% of the merchandise subtotal, with a minimum of $9.00. "
        "Orders shipped within Canada do not include this fee.",
    ),
    (
        60,
        "How can I pay?",
        "Checkout is through PayPal. You can pay with PayPal, Pay Later, or a "
        "debit or credit card.",
    ),
]


def seed_launch_faqs(apps, schema_editor):
    FAQ = apps.get_model('General', 'FAQ')
    for sort_order, title, content in LAUNCH_FAQS:
        FAQ.objects.get_or_create(
            title=title,
            defaults={
                'content': content,
                'sort_order': sort_order,
            },
        )


def unseed_launch_faqs(apps, schema_editor):
    # Only remove rows that still match the seed. An edited answer stays.
    FAQ = apps.get_model('General', 'FAQ')
    for _sort_order, title, content in LAUNCH_FAQS:
        FAQ.objects.filter(title=title, content=content).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('General', '0012_faq_sort_order'),
    ]

    operations = [
        migrations.RunPython(seed_launch_faqs, unseed_launch_faqs),
    ]
