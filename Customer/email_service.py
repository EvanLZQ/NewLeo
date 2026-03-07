import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

SITE_URL = 'https://www.eyelovewear.com'


def send_welcome_email(customer) -> None:
    """Send a welcome email after a new user registers."""
    if not customer.email:
        logger.warning('send_welcome_email: customer has no email — skipped.')
        return

    first_name = customer.first_name or customer.username or 'there'

    context = {
        'customer':   customer,
        'first_name': first_name,
        'site_url':   SITE_URL,
    }

    subject      = 'Welcome to Eyelovewear! 👓'
    html_content = render_to_string('email/welcome.html', context)
    text_content = (
        f'Welcome to Eyelovewear, {first_name}!\n\n'
        f'Your account is ready. Browse our collection at {SITE_URL}/products'
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer.email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    logger.info('Welcome email sent to %s', customer.email)


def send_newsletter_confirmation(email: str) -> None:
    """Send a subscription confirmation email to a new newsletter subscriber."""
    if not email:
        return

    context = {
        'email':    email,
        'site_url': SITE_URL,
    }

    subject      = "You're subscribed to Eyelovewear updates!"
    html_content = render_to_string('email/newsletter_welcome.html', context)
    text_content = (
        f"You've subscribed to Eyelovewear newsletter updates.\n\n"
        f"Browse our collection at {SITE_URL}/products"
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    logger.info('Newsletter confirmation sent to %s', email)
