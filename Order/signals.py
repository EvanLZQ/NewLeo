import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import OrderInfo

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=OrderInfo)
def stash_original_order_values(sender, instance, **kwargs):
    """
    Before saving, read the current DB values and stash them on the instance
    so the post_save signal can detect what actually changed.
    """
    if instance.pk:
        try:
            original = OrderInfo.objects.get(pk=instance.pk)
            instance._pre_save_status   = original.order_status
            instance._pre_save_tracking = original.tracking_number
        except OrderInfo.DoesNotExist:
            instance._pre_save_status   = None
            instance._pre_save_tracking = None
    else:
        # New record — nothing to compare against
        instance._pre_save_status   = None
        instance._pre_save_tracking = None


@receiver(post_save, sender=OrderInfo)
def order_updated_handler(sender, instance, created, **kwargs):
    """
    After saving, check if order_status or tracking_number changed and send
    a status update email if so.  New orders (created=True) are skipped here
    because the confirmation email is sent separately in confirmPayment view.
    """
    if created:
        return

    old_status   = getattr(instance, '_pre_save_status',   None)
    old_tracking = getattr(instance, '_pre_save_tracking', None)

    status_changed   = old_status   != instance.order_status
    tracking_changed = old_tracking != instance.tracking_number

    if not (status_changed or tracking_changed):
        return

    from Order.email_service import send_order_status_update
    try:
        send_order_status_update(instance)
    except Exception:
        logger.exception(
            'Failed to send status update email for order %s', instance.order_number
        )
