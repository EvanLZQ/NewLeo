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


def send_password_reset_code(email: str, code: str, first_name: str = '') -> None:
    """Send a 6-digit password reset verification code."""
    if not email:
        logger.warning('send_password_reset_code: no email — skipped.')
        return

    display_name = first_name or 'there'

    context = {
        'code':       code,
        'first_name': display_name,
        'site_url':   SITE_URL,
    }

    subject      = 'Your Eyelovewear Password Reset Code'
    html_content = render_to_string('email/password_reset.html', context)
    text_content = (
        f'Hi {display_name},\n\n'
        f'Your password reset verification code is: {code}\n\n'
        f'This code expires in 10 minutes. If you did not request this, '
        f'you can safely ignore this email.\n\n'
        f'— Eyelovewear'
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    logger.info('Password reset code sent to %s', email)
