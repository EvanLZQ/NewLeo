from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import CurrencyConversion, FAQ, PageImage, NewsletterSubscriber
from .serializer import CurrencySerializer, FAQSerializer, PageImageSerializer
from django.conf import settings
from django.http import HttpResponse
from django.utils.xmlutils import SimplerXMLGenerator
from io import StringIO

# Create your views here.


@api_view(['GET'])
def getCurrencyConversion(request):
    currency = CurrencyConversion.objects.all()
    serializer = CurrencySerializer(currency, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getFAQContents(request):
    faq = FAQ.objects.all()
    serializer = FAQSerializer(faq, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getPageImage(request):
    imgPage = request.query_params.get('page')
    imgSection = request.query_params.get('section')
    pageImages = PageImage.objects.filter(
        page=imgPage, section=imgSection)
    serializer = PageImageSerializer(pageImages, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
def subscribe_newsletter(request):
    """
    Subscribe an email address to the newsletter.
    Returns the same 200 response whether the address is new or already subscribed
    to prevent email enumeration.
    """
    email = request.data.get('email', '').strip().lower()

    if not email:
        return Response({'error': 'Email is required.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return Response({'error': 'Please enter a valid email address.'}, status=400)

    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=email,
        defaults={'is_active': True},
    )

    if not created and not subscriber.is_active:
        # Re-activate a previously unsubscribed address
        subscriber.is_active = True
        subscriber.save(update_fields=['is_active'])
        created = True  # treat re-subscribe the same as new for email purposes

    if created:
        try:
            from Customer.email_service import send_newsletter_confirmation
            send_newsletter_confirmation(email)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Failed to send newsletter confirmation to %s', email)

    return Response({'message': 'Thank you for subscribing!'}, status=200)


# Public pages worth indexing. Account, cart, checkout, order tracking and the
# lens flow are deliberately absent (private or per-visitor state).
SITEMAP_STATIC_PATHS = [
    ('/', 'daily', '1.0'),
    ('/products', 'daily', '0.9'),
    ('/blogs', 'weekly', '0.6'),
    ('/FAQ', 'monthly', '0.5'),
    ('/why_choose_us', 'monthly', '0.4'),
    ('/our_story', 'monthly', '0.4'),
    ('/contact', 'monthly', '0.4'),
    ('/ourLens', 'monthly', '0.4'),
    ('/prescription_guide', 'monthly', '0.5'),
    ('/face-shape-quiz', 'monthly', '0.7'),
    ('/face-shape/oval', 'monthly', '0.7'),
    ('/face-shape/round', 'monthly', '0.7'),
    ('/face-shape/square', 'monthly', '0.7'),
    ('/face-shape/heart', 'monthly', '0.7'),
    ('/face-shape/diamond', 'monthly', '0.7'),
    ('/face-shape/oblong', 'monthly', '0.7'),
]


def sitemap_xml(request):
    """
    /api/general/sitemap.xml — home, listing and static pages, every online
    frame's detail page, and every blog post. Built from the live database on
    each request (a few hundred rows at most); crawlers hit it rarely.
    """
    from Product.models import ProductInfo
    from Blog.models import BlogInfo

    base = getattr(settings, 'SITE_BASE_URL', 'https://www.eyelovewear.com').rstrip('/')

    entries = [(path, None, freq, prio) for path, freq, prio in SITEMAP_STATIC_PATHS]

    # Same URL the product cards link to: /products/<model>/<first sku>
    products = (
        ProductInfo.objects
        .filter(productInstance__online=True)
        .distinct()
        .prefetch_related('productInstance')
    )
    for product in products:
        instance = next(
            (i for i in product.productInstance.all() if i.online), None)
        if instance is None:
            continue
        entries.append((f'/products/{product.model_number}/{instance.sku}',
                        None, 'weekly', '0.8'))

    for blog in BlogInfo.objects.exclude(slug__isnull=True).exclude(slug=''):
        entries.append((f'/blogs/{blog.slug}', blog.updated_at.date().isoformat(),
                        'monthly', '0.5'))

    out = StringIO()
    xml = SimplerXMLGenerator(out, 'utf-8')
    xml.startDocument()
    xml.startElement('urlset',
                     {'xmlns': 'http://www.sitemaps.org/schemas/sitemap/0.9'})
    for path, lastmod, freq, prio in entries:
        xml.startElement('url', {})
        for tag, value in (('loc', base + path), ('lastmod', lastmod),
                           ('changefreq', freq), ('priority', prio)):
            if value:
                xml.addQuickElement(tag, value)
        xml.endElement('url')
    xml.endElement('urlset')
    xml.endDocument()
    return HttpResponse(out.getvalue(), content_type='application/xml')


CONTACT_MAX_PER_HOUR = 5


@api_view(['POST'])
@permission_classes([AllowAny])
def contact_us(request):
    """
    Storefront "Contact us" form. Saves the message as a CustomerMessage
    (Django admin > Customer Messages), linked to the account when the
    visitor is signed in. If CONTACT_NOTIFY_EMAIL is configured, staff also
    get an email copy.
    """
    from django.core.cache import cache
    from Customer.models import CustomerMessage
    from Leoptique.client_ip import get_client_ip

    name = (request.data.get('name') or '').strip()[:100]
    email = (request.data.get('email') or '').strip().lower()
    order_number = (request.data.get('order_number') or '').strip()[:40]
    message = (request.data.get('message') or '').strip()

    if not email or not message:
        return Response({'error': 'Email and message are required.'}, status=400)
    try:
        validate_email(email)
    except ValidationError:
        return Response({'error': 'Please enter a valid email address.'}, status=400)
    if len(message) > 5000:
        return Response({'error': 'Message is too long (5000 characters max).'}, status=400)

    rl_key = f'rl:contact:{get_client_ip(request)}'
    sent = cache.get(rl_key, 0)
    if sent >= CONTACT_MAX_PER_HOUR:
        return Response({'error': 'Too many messages. Please try again later.'}, status=429)
    cache.set(rl_key, sent + 1, 3600)

    user = request.user if request.user and request.user.is_authenticated else None
    subject = f'Contact form: {order_number or name or email}'[:100]
    content = (
        f'From: {name or "(no name)"} <{email}>\n'
        f'Order number: {order_number or "-"}\n'
        f'Signed in as: {user.username if user else "guest"}\n\n'
        f'{message}'
    )
    CustomerMessage.objects.create(
        customer=user, subject=subject, content=content, message_from='Customer')

    notify = getattr(settings, 'CONTACT_NOTIFY_EMAIL', '')
    if notify:
        try:
            from django.core.mail import EmailMessage
            EmailMessage(
                subject=subject, body=content, from_email=settings.DEFAULT_FROM_EMAIL,
                to=[notify], reply_to=[email],
            ).send()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Failed to email contact message from %s', email)

    return Response({'message': "Thanks! We've received your message and will reply by email."}, status=201)
