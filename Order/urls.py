from django.urls import path
from . import views
from . import stripe_checkout

urlpatterns = [
    path('allorders', views.getAllOrders, name='orders'),
    path('<int:id>', views.getTargetOrder, name='get_target_order'),
    path('completeset', views.getCompleteSet, name='completesets'),
    path('createcompleteset', views.createCompleteSet, name='create_completeset'),
    path('deletecompleteset/<int:set_id>',
         views.deleteCompleteSet, name='delete_completeset'),
    path('completeset/<int:set_id>',
         views.getTargetCompleteSet, name='get_target_set'),
    path('completesetloader/<int:set_id>',
         views.getCompleteSetLoader, name='get_set_loader'),
    path('updatecompleteset/<int:set_id>',
         views.updateCompleteSet, name='update_target_set'),
    # Payment flow
    path('validate_coupon', views.validateCoupon, name='validate_coupon'),
    path('create_pending', views.createPendingOrder, name='create_pending_order'),
    path('confirm_payment', views.confirmPayment, name='confirm_payment'),
    path('cancel_pending/<int:order_id>', views.cancelPendingOrder, name='cancel_pending_order'),
    # Guest checkout
    path('guest_cart', views.guestCart, name='guest_cart'),
    path('create_pending_guest', views.createPendingOrderGuest, name='create_pending_order_guest'),
    path('confirm_payment_guest', views.confirmPaymentGuest, name='confirm_payment_guest'),
    path('cancel_pending_guest/<int:order_id>', views.cancelPendingOrderGuest, name='cancel_pending_order_guest'),
    path('guest_lookup', views.guestOrderLookup, name='guest_order_lookup'),
    path('track', views.trackOrder, name='track_order'),
    # Stripe Checkout (second payment method; 404 unless STRIPE_ENABLED)
    path('stripe/create_session', stripe_checkout.createStripeSession, name='stripe_create_session'),
    path('stripe/session_status', stripe_checkout.stripeSessionStatus, name='stripe_session_status'),
    path('stripe/webhook', stripe_checkout.stripeWebhook, name='stripe_webhook'),
]
