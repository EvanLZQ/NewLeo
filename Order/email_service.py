import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

STATUS_SUBJECTS = {
    'PROCESSING': 'Your Eyelovewear order is being processed',
    'SHIPPED':    'Your Eyelovewear order has shipped! 🚚',
    'DELIVERED':  'Your Eyelovewear order has been delivered! 🎉',
    'CANCELLED':  'Your Eyelovewear order has been cancelled',
    'COMPLETE':   'Your Eyelovewear order is complete',
    'REFUND':     'Refund update for your Eyelovewear order',
}

# Statuses that should NOT trigger an email (internal / not meaningful to customer)
SKIP_STATUSES = {'NULL', 'UNPAID'}


def send_order_confirmation(order) -> None:
    """
    Send an order confirmation email after successful payment.
    Called directly from confirmPayment view.
    """
    if not order.email:
        logger.warning('send_order_confirmation: order %s has no email — skipped.', order.order_number)
        return

    complete_sets = order.completeset_set.select_related(
        'frame', 'usage', 'color', 'coating', 'index', 'prescription'
    ).all()

    context = {
        'order': order,
        'complete_sets': complete_sets,
        'site_url': 'https://www.eyelovewear.com',
    }

    subject = f'Order Confirmed: {order.order_number}'
    html_content = render_to_string('email/order_confirmation.html', context)
    text_content = (
        f'Thank you for your order!\n\n'
        f'Order Number: {order.order_number}\n'
        f'Total: ${order.total_amount}\n\n'
        f'View your order at https://www.eyelovewear.com/user/order'
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    logger.info('Order confirmation sent for %s to %s', order.order_number, order.email)


def send_order_status_update(order) -> None:
    """
    Send an order status update email when order_status or tracking_number changes.
    Called from the post_save signal (Order/signals.py).
    """
    if not order.email:
        return
    if order.order_status in SKIP_STATUSES:
        return

    complete_sets = order.completeset_set.select_related('frame').all()

    context = {
        'order': order,
        'complete_sets': complete_sets,
        'site_url': 'https://www.eyelovewear.com',
    }

    subject = STATUS_SUBJECTS.get(
        order.order_status,
        f'Update on your order {order.order_number}',
    )
    html_content = render_to_string('email/order_status_update.html', context)
    text_content = (
        f'Your order {order.order_number} has been updated.\n\n'
        f'Status: {order.order_status}\n'
        f'View details at https://www.eyelovewear.com/user/order'
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    logger.info('Status update email sent for %s (%s) to %s', order.order_number, order.order_status, order.email)
