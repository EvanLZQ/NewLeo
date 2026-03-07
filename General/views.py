from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import CurrencyConversion, FAQ, PageImage, NewsletterSubscriber
from .serializer import CurrencySerializer, FAQSerializer, PageImageSerializer

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
    return Response(serializer)


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
