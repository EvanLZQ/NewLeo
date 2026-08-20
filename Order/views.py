import uuid
import datetime
import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework.response import Response
from django.http import JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
import paypalrestsdk

from Leoptique.authentication import AccessTokenAuthentication
from .models import *
from .serializer import CompleteSetSerializer, OrderSerializer, CompleteSetObjectSerializer
from .service.order_service import OrderService

paypalrestsdk.configure({
    "mode": settings.PAYPAL_MODE,
    "client_id": settings.PAYPAL_CLIENT_ID,
    "client_secret": settings.PAYPAL_CLIENT_SECRET,
})

AUTH_CLASSES = [SessionAuthentication, AccessTokenAuthentication]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_owns_complete_set(user, set_id):
    """Check if a CompleteSet belongs to the user's cart or an order they own."""
    cart = getattr(user, 'shopping_cart', None)
    if cart and cart.eyeglasses_set.filter(id=set_id).exists():
        return True
    return CompleteSet.objects.filter(id=set_id, order__customer=user).exists()


def _caller_owns_complete_set(request, set_id):
    """
    Ownership check that works for both authenticated users and guests.
    - Authenticated: delegates to _user_owns_complete_set.
    - Guest: checks if the CompleteSet is in the session's guest cart, OR
      is unattached (just created, not yet linked to any order/cart).
    """
    if request.user and request.user.is_authenticated:
        return _user_owns_complete_set(request.user, set_id)

    from Customer.models import ShoppingCart as ShoppingCartModel
    guest_cart_id = request.session.get('guest_cart_id')
    if guest_cart_id and ShoppingCartModel.objects.filter(
            pk=guest_cart_id, eyeglasses_set__id=set_id).exists():
        return True
    # Allow operating on unattached sets (just created, not in any cart/order yet)
    return CompleteSet.objects.filter(id=set_id, order=None).exists()


def generate_order_number():
    """Produce a unique order number like ELW-20260226-A3F7B1."""
    today = datetime.datetime.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"ELW-{today}-{suffix}"


# An UNPAID order left untouched this long is treated as abandoned and
# eligible for automatic cleanup (see _cancel_orders / Step 0b below).
PENDING_ORDER_EXPIRY = datetime.timedelta(minutes=30)


def _cancel_orders(queryset):
    """
    Cancel a queryset of UNPAID OrderInfo rows WITHOUT deleting them: detach
    their CompleteSet items (order=None, freeing them to be re-added to a
    cart or a new order) and mark order_status='CANCELED'. The row itself
    stays — deleting it is what used to make a customer's own "My Orders"
    list show a real order that 404'd the instant they clicked into it,
    because some unrelated, later checkout attempt had silently erased it.
    payment_status stays 'UNPAID' (that part remains true); order_status is
    what communicates "this attempt is over."
    """
    ids = list(queryset.values_list('pk', flat=True))
    if not ids:
        return
    CompleteSet.objects.filter(order_id__in=ids).update(order=None)
    OrderInfo.objects.filter(pk__in=ids).update(order_status='CANCELED')


# ── PayPal server-side verification ─────────────────────────────────────────
# `paypalrestsdk` (imported above) only speaks PayPal's legacy Payments v1
# API. The frontend's PayPal JS SDK (PayPalButton.tsx) creates/captures
# orders via the newer Orders v2 API, which paypalrestsdk doesn't cover — so
# verification here talks to Orders v2 directly over REST instead of trying
# to reuse that SDK.

PAYPAL_API_BASE = (
    'https://api-m.paypal.com' if settings.PAYPAL_MODE == 'live'
    else 'https://api-m.sandbox.paypal.com'
)


def _get_paypal_access_token():
    resp = requests.post(
        f'{PAYPAL_API_BASE}/v1/oauth2/token',
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        data={'grant_type': 'client_credentials'},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def _fetch_paypal_order(paypal_order_id):
    """
    Fetch an order directly from PayPal's own servers — the only source of
    truth for whether a payment actually happened, since the browser (and
    therefore anything it POSTs to us) can't be trusted. Returns the parsed
    JSON response, or None if the lookup fails for any reason (network
    error, bad credentials, PayPal outage, unknown order id, ...).
    """
    try:
        token = _get_paypal_access_token()
        resp = requests.get(
            f'{PAYPAL_API_BASE}/v2/checkout/orders/{paypal_order_id}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logging.getLogger(__name__).exception(
            'Failed to verify PayPal order %s', paypal_order_id)
        return None


def _verify_and_extract_capture(paypal_order_id, expected_minimum_total):
    """
    Independently confirm a PayPal order actually completed and paid at
    least `expected_minimum_total` (our server-computed sub_total +
    shipping). Returns (capture_id, captured_amount, payer_email) on
    success, or (None, None, error_message) on failure.

    NOTE: tax is currently computed client-side only and never sent to or
    stored by the backend (see order_service.py / PaymentForm.tsx), so this
    checks "captured >= our base total" rather than an exact match — it
    closes the "pay nothing / pay an arbitrary low amount" hole, but can't
    yet verify the tax-inclusive figure precisely. That needs tax to become
    a server-computed, server-stored value first.
    """
    paypal_order = _fetch_paypal_order(paypal_order_id)
    if paypal_order is None:
        return None, None, 'Could not verify payment with PayPal'

    if paypal_order.get('status') != 'COMPLETED':
        return None, None, 'PayPal payment not completed'

    try:
        capture = paypal_order['purchase_units'][0]['payments']['captures'][0]
        captured_amount = Decimal(capture['amount']['value'])
        capture_id = capture['id']
    except (KeyError, IndexError, InvalidOperation, TypeError):
        return None, None, 'Unexpected PayPal response shape'

    if captured_amount < expected_minimum_total:
        return None, None, 'Captured amount is less than the order total'

    payer_email = (paypal_order.get('payer') or {}).get('email_address', '')
    return capture_id, captured_amount, payer_email


# ── CompleteSet CRUD ─────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def getCompleteSet(request):
    cart = getattr(request.user, 'shopping_cart', None)
    cart_set_ids = list(cart.eyeglasses_set.values_list('id', flat=True)) if cart else []
    order_set_ids = list(
        CompleteSet.objects.filter(order__customer=request.user).values_list('id', flat=True)
    )
    all_ids = set(cart_set_ids + order_set_ids)
    sets = CompleteSet.objects.filter(id__in=all_ids)
    serializer = CompleteSetSerializer(sets, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([AllowAny])
def deleteCompleteSet(request, set_id):
    if not _caller_owns_complete_set(request, set_id):
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        complete_set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    complete_set.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def build_price_check(request_data, instance):
    """
    Compare the frontend-submitted sub_total against the backend-calculated
    sub_total on the newly-created CompleteSet, and return a structured
    price_check dict for the API response.

    frontend_price_snapshot (optional in request body):
        { frame, usage, color, coating, index }  — the prices the frontend
        used when it calculated its sub_total.  Enables a per-item diff.
        Defaults to 0 for any missing key (shows full backend price as delta).
    """
    frontend_sub_total = float(request_data.get('sub_total') or 0)
    backend_sub_total  = float(instance.sub_total)
    snapshot           = request_data.get('frontend_price_snapshot') or {}

    breakdown = []

    # ── Frame ────────────────────────────────────────────────────────────────
    backend_frame  = float(instance.frame.price) if instance.frame else 0.0
    frontend_frame = float(snapshot.get('frame') or 0)
    breakdown.append({
        'component':      'frame',
        'label':          f'Frame ({instance.frame.sku})',
        'frontend_price': frontend_frame,
        'backend_price':  backend_frame,
        'changed':        abs(backend_frame - frontend_frame) > 0.005,
    })

    # ── Lens options (skip null FKs — e.g. color_option is null when the
    #    selected function path doesn't require a color step) ──────────────
    for component, option_obj, price_field, label_field in [
        ('function_path',   instance.function_path,   'extra_price', 'function_label'),
        ('tint_type',       instance.tint_type,        'extra_price', 'function_label'),
        ('index_option',    instance.index_option,     'price',       'option_label'),
        ('color_option',    instance.color_option,     'extra_price', 'color_name'),
        ('reader_strength', instance.reader_strength,  'price',       'label'),
    ]:
        if option_obj is None:
            continue
        backend_p  = float(getattr(option_obj, price_field))
        frontend_p = float(snapshot.get(component) or 0)
        breakdown.append({
            'component':      component,
            'label':          getattr(option_obj, label_field),
            'frontend_price': frontend_p,
            'backend_price':  backend_p,
            'changed':        abs(backend_p - frontend_p) > 0.005,
        })

    # ── Coatings — many-to-many now (stacked add-ons), one breakdown entry
    #    per attached coating. frontend_price_snapshot['coatings'], if sent,
    #    is expected as {coating_id: price}; anything missing defaults to 0
    #    same as every other component above.
    coating_snapshot = snapshot.get('coatings') or {}
    for coating in instance.coatings.all():
        backend_p  = float(coating.price)
        frontend_p = float(coating_snapshot.get(str(coating.id)) or 0)
        breakdown.append({
            'component':      f'coating_{coating.id}',
            'label':          coating.label,
            'frontend_price': frontend_p,
            'backend_price':  backend_p,
            'changed':        abs(backend_p - frontend_p) > 0.005,
        })

    difference = round(backend_sub_total - frontend_sub_total, 2)
    return {
        'match':              abs(difference) < 0.005,
        'frontend_sub_total': frontend_sub_total,
        'backend_sub_total':  backend_sub_total,
        'difference':         difference,   # positive = price went up
        'breakdown':          breakdown,
    }


@api_view(['POST'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([AllowAny])
def createCompleteSet(request):
    if request.method == 'POST':
        serializer = CompleteSetSerializer(
            data=request.data, context={'request': request})
        if serializer.is_valid():
            instance = serializer.save()
            response_data = dict(serializer.data)
            response_data['price_check'] = build_price_check(request.data, instance)
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([AllowAny])
def getTargetCompleteSet(request, set_id):
    if not _caller_owns_complete_set(request, set_id):
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        complete_set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CompleteSetSerializer(complete_set, many=False)
    return Response(serializer.data)


@api_view(['PATCH'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([AllowAny])
def updateCompleteSet(request, set_id):
    if not _caller_owns_complete_set(request, set_id):
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        complete_set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CompleteSetSerializer(
        instance=complete_set, data=request.data, partial=True, context={'request': request}
    )
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Order views ──────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def getAllOrders(request):
    orders = OrderInfo.objects.filter(customer=request.user)
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def getTargetOrder(request, id):
    try:
        order = OrderInfo.objects.get(id=id, customer=request.user)
    except OrderInfo.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = OrderSerializer(order)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([AllowAny])
def getCompleteSetLoader(request, set_id):
    if not _caller_owns_complete_set(request, set_id):
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        complete_set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CompleteSetObjectSerializer(complete_set, many=False)
    return Response(serializer.data)


# ── Order helpers ─────────────────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def createPendingOrder(request):
    """
    Create a pending (UNPAID) OrderInfo from the items in the customer's cart.

    Request body:
        complete_set_ids  – list[int]   IDs of CompleteSet rows to attach
        address_id        – int         FK to General.Address
        shipping_method   – str         e.g. "Primary express" / "Xpresspost" / "UPS"
        country           – str         e.g. "United States"  (used for shipping calc)
        email             – str         customer e-mail for the order record

    Response (201):
        { order_id, order_number, sub_total, shipping_cost, total_before_tax }
    """
    data             = request.data
    complete_set_ids = data.get('complete_set_ids', [])
    address_id       = data.get('address_id')
    shipping_method  = data.get('shipping_method', '')
    country          = data.get('country', '')
    email            = data.get('email', '') or ''
    # Always prefer the authenticated user's e-mail over whatever the client sends.
    email = getattr(request.user, 'email', None) or getattr(request.user, 'username', None) or email

    if not complete_set_ids:
        return Response(
            {'error': 'complete_set_ids is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Every requested item must actually belong to this customer — otherwise
    # Step 0a below (which cancels whatever UNPAID order currently holds a
    # requested item) could be pointed at a stranger's in-progress checkout.
    if not all(_user_owns_complete_set(request.user, cs_id) for cs_id in complete_set_ids):
        return Response(
            {'error': 'One or more complete sets do not belong to you'},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        # ── Step 0a: item-based cleanup (runs BEFORE validation) ─────────────
        # Cancel any UNPAID orders that currently own the requested items,
        # regardless of who created them.  This recovers items stuck because of:
        #   • Orders created before customer= FK was added  (customer=NULL)
        #   • Frontend cancel failures  (network error, page refresh, tab close)
        # ALL CompleteSet rows on those orders are freed — not just the requested
        # ones — so the order is left in a consistent state.
        _cancel_orders(
            OrderInfo.objects.filter(
                completeset__id__in=complete_set_ids,
                payment_status='UNPAID',
            ).exclude(order_status='CANCELED').distinct()
        )

        # ── Step 0b: age-based expiry ─────────────────────────────────────────
        # Cancel this customer's OTHER unpaid orders, but only ones that have
        # actually gone stale (no payment for PENDING_ORDER_EXPIRY) — not every
        # unrelated pending order just because they're checking out again.
        # Wiping out everything unconditionally on every checkout attempt is
        # what produced ghost 404s: a customer could still be looking at (or
        # about to click into) an order that a separate, later checkout
        # attempt had already erased.
        expiry_cutoff = timezone.now() - PENDING_ORDER_EXPIRY
        _cancel_orders(
            OrderInfo.objects.filter(
                customer=request.user,
                payment_status='UNPAID',
                created_at__lt=expiry_cutoff,
            ).exclude(order_status='CANCELED')
        )

        # ── Validate (after cleanup so freed items now pass) ────────────────────
        # select_for_update() locks these specific rows for the rest of this
        # transaction: a second, overlapping createPendingOrder call for any
        # of the same items has to wait here until we commit, then re-reads
        # their now-current state — closing the race where two concurrent
        # requests could otherwise both pass this check before either one
        # actually claimed the items, leaving one of them with an OrderInfo
        # row that has a total but no real items attached.
        locked_sets = list(
            CompleteSet.objects.select_for_update().filter(id__in=complete_set_ids)
        )
        valid_sets = [
            cs for cs in locked_sets if cs.order_id is None and not cs.saved_for_later
        ]
        if len(valid_sets) != len(complete_set_ids):
            return Response(
                {'error': 'One or more complete sets are invalid or already attached to an order'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Address snapshot ─────────────────────────────────────────────────
        # Clone the customer's saved address into a dedicated row for this
        # order rather than pointing at the live one — editing or deleting a
        # saved address later must not change what a past order says it
        # shipped to.
        from General.models import Address
        try:
            source_address = Address.objects.get(pk=address_id, customer=request.user)
        except Address.DoesNotExist:
            return Response({'error': 'Invalid address_id'}, status=status.HTTP_400_BAD_REQUEST)
        order_address = Address.objects.create(
            customer=request.user,
            full_name=source_address.full_name,
            phone=source_address.phone,
            address=source_address.address,
            city=source_address.city,
            province_state=source_address.province_state,
            country=source_address.country,
            post_code=source_address.post_code,
        )

        # ── Step 1: create the OrderInfo shell ─────────────────────────────────
        try:
            order = OrderInfo(
                customer=request.user,
                email=email,
                order_number=generate_order_number(),
                order_status='PROCESSING',
                payment_status='UNPAID',
                payment_type='paypal',
                address=order_address,
                shipping_company=shipping_method,
                comment='',
                refound_status='',
                refound_amount=0,
                sub_total=0,
                shipping_cost=0,
                total_amount=0,
            )
            order.save()
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # ── Step 2: link the complete sets ─────────────────────────────────────
        CompleteSet.objects.filter(id__in=complete_set_ids).update(order=order)

        # ── Step 3: calculate totals ───────────────────────────────────────────
        order.sub_total     = OrderService.calculate_sub_total(order)
        order.shipping_cost = OrderService.calculate_shipping_cost(
            country, float(order.sub_total), shipping_method,
        )
        order.total_amount  = order.sub_total + order.shipping_cost

        OrderInfo.objects.filter(pk=order.pk).update(
            sub_total=order.sub_total,
            shipping_cost=order.shipping_cost,
            total_amount=order.total_amount,
        )

    return Response(
        {
            'order_id':         order.pk,
            'order_number':     order.order_number,
            'sub_total':        str(order.sub_total),
            'shipping_cost':    str(order.shipping_cost),
            'total_before_tax': str(order.total_amount),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def confirmPayment(request):
    """
    Record a completed PayPal payment and mark the order as PAID.

    Request body:
        order_id         – int    our internal OrderInfo PK
        paypal_order_id  – str    PayPal order ID (from actions.order.capture()'s
                                   `details.id`) — looked up directly against
                                   PayPal's own servers below, never trusted
                                   as-is.

    Response (200):
        { success: true, order_number }
    """
    data              = request.data
    order_id          = data.get('order_id')
    paypal_order_id   = data.get('paypal_order_id', '')

    if not order_id:
        return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not paypal_order_id:
        return Response({'error': 'paypal_order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        try:
            order = OrderInfo.objects.select_for_update().get(
                pk=order_id, customer=request.user)
        except OrderInfo.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == 'PAID':
            return Response({'error': 'Order is already paid'}, status=status.HTTP_400_BAD_REQUEST)

        # A given PayPal payment can only ever settle one of our orders —
        # otherwise the same legitimate capture could be replayed against
        # multiple OrderInfo rows.
        if OrderPayment.objects.filter(gateway_transaction_id=paypal_order_id).exists():
            return Response({'error': 'This PayPal payment has already been used'},
                             status=status.HTTP_400_BAD_REQUEST)

        capture_id, captured_amount, result = _verify_and_extract_capture(
            paypal_order_id, order.total_amount)
        if capture_id is None:
            return Response({'error': result}, status=status.HTTP_400_BAD_REQUEST)
        payer_email = result

        # Create the payment record — everything here comes from PayPal's own
        # response (fetched server-side above), not from client input.
        OrderPayment.objects.create(
            transaction_id=capture_id,
            order=order,
            payment_gateway='paypal',
            transaction_amount=str(captured_amount),
            payer_email=payer_email,
            gateway_transaction_id=paypal_order_id,
            payment_response=data.get('payment_response', {}),
            transaction_status='completed',
        )

        # Mark the order PAID
        OrderInfo.objects.filter(pk=order.pk).update(
            payment_status='PAID',
            payment_type='paypal',
        )

    # Remove paid items from all shopping carts (they've been purchased).
    from Customer.models import ShoppingCart as ShoppingCartModel
    paid_set_ids = list(CompleteSet.objects.filter(order=order).values_list('id', flat=True))
    if paid_set_ids:
        for cart in ShoppingCartModel.objects.filter(eyeglasses_set__id__in=paid_set_ids).distinct():
            cart.eyeglasses_set.remove(*paid_set_ids)

    # Send order confirmation email — wrapped so a mail failure never breaks the response
    try:
        order.refresh_from_db()
        from Order.email_service import send_order_confirmation
        send_order_confirmation(order)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send order confirmation email for order %s', order.order_number
        )

    return Response(
        {'success': True, 'order_number': order.order_number},
        status=status.HTTP_200_OK,
    )


@api_view(['DELETE'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def cancelPendingOrder(request, order_id):
    """
    Cancel a pending (UNPAID) order created by createPendingOrder.

    Unlinks the attached CompleteSet objects (so they return to the cart) and
    marks the OrderInfo as CANCELED rather than deleting it — it stays visible
    in the customer's order history. Used when the user goes back from the
    Payment step.
    """
    try:
        order = OrderInfo.objects.get(
            pk=order_id, payment_status='UNPAID', customer=request.user)
    except OrderInfo.DoesNotExist:
        return Response({'error': 'Pending order not found'}, status=status.HTTP_404_NOT_FOUND)

    _cancel_orders(OrderInfo.objects.filter(pk=order.pk))

    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Legacy PayPal View (unwired — kept for reference) ─────────────────────────
def payment(request):

    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal",
        },
        "redirect_urls": {
            "return_url": "https://admin.eyelovewear.com/payment/execute/",
            "cancel_url": "https://admin.eyelovewear.com/payment/canceled/",
        },
        "transactions": [{
            "amount": {
                "total": "10.00",
                "currency": "USD"
            },
            "description": "Testing PayPal payment transaction."
        }]
    })

    if payment.create():
        for link in payment.links:
            if link.rel == "approval_url":
                approval_url = str(link.href)
                return redirect(approval_url)
    else:
        return JsonResponse({'error': 'payment not created'})


# ── Guest checkout helpers ────────────────────────────────────────────────────

def _get_or_create_guest_cart(request):
    """Return a ShoppingCart tied to the current Django session."""
    from Customer.models import ShoppingCart as ShoppingCartModel
    cart_id = request.session.get('guest_cart_id')
    if cart_id:
        try:
            return ShoppingCartModel.objects.get(pk=cart_id)
        except ShoppingCartModel.DoesNotExist:
            pass
    cart = ShoppingCartModel.objects.create()
    request.session['guest_cart_id'] = cart.pk
    return cart


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def guestCart(request):
    """
    Manage a session-based shopping cart for unauthenticated users.

    POST body:
        action           – "get" | "add" | "remove"
        complete_set_id  – int (required for add/remove)
    """
    from Customer.serializer import ShoppingCartSerializer
    action = request.data.get('action', 'get')
    cart = _get_or_create_guest_cart(request)

    if action == 'add':
        cs_id = request.data.get('complete_set_id')
        # Only unattached items are claimable — same rule as the
        # authenticated path (ShoppingCartSerializer.update), just without
        # an "already my own order" exception since guests have no identity
        # beyond this session.
        if cs_id and CompleteSet.objects.filter(id=cs_id, order__isnull=True).exists():
            cart.eyeglasses_set.add(cs_id)
    elif action == 'remove':
        cs_id = request.data.get('complete_set_id')
        if cs_id:
            cart.eyeglasses_set.remove(cs_id)

    serializer = ShoppingCartSerializer(cart)
    return Response(serializer.data)


# ── Guest order creation ──────────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def createPendingOrderGuest(request):
    """
    Create a pending (UNPAID) OrderInfo for a guest (unauthenticated) user.

    Request body:
        complete_set_ids  – list[int]
        email             – str  (required)
        address_data      – dict {full_name, phone, address, city, province_state, country, post_code}
        shipping_method   – str
        country           – str
    """
    from General.models import Address

    data             = request.data
    complete_set_ids = data.get('complete_set_ids', [])
    email            = (data.get('email') or '').strip()
    address_data     = data.get('address_data', {})
    shipping_method  = data.get('shipping_method', '')
    country          = data.get('country', '')

    if not email:
        return Response({'error': 'Email is required for guest checkout'},
                        status=status.HTTP_400_BAD_REQUEST)
    if not complete_set_ids:
        return Response({'error': 'complete_set_ids is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    required_addr = ['full_name', 'phone', 'address', 'city', 'province_state', 'country', 'post_code']
    for field in required_addr:
        if not address_data.get(field, '').strip():
            return Response({'error': f'{field} is required in address_data'},
                            status=status.HTTP_400_BAD_REQUEST)

    if not all(_caller_owns_complete_set(request, cs_id) for cs_id in complete_set_ids):
        return Response(
            {'error': 'One or more complete sets do not belong to you'},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        # Step 0a: item-based cleanup — same as authenticated
        _cancel_orders(
            OrderInfo.objects.filter(
                completeset__id__in=complete_set_ids,
                payment_status='UNPAID',
            ).exclude(order_status='CANCELED').distinct()
        )

        # Step 0b: session-based cleanup — cancel previous guest pending order
        # (already scoped to this one session-tracked order, not a blanket
        # sweep, so no age check needed here like the authenticated path).
        prev_order_id = request.session.get('guest_pending_order_id')
        if prev_order_id:
            _cancel_orders(
                OrderInfo.objects.filter(
                    pk=prev_order_id, payment_status='UNPAID',
                ).exclude(order_status='CANCELED')
            )

        # Validate — locked, same reasoning as createPendingOrder above.
        locked_sets = list(
            CompleteSet.objects.select_for_update().filter(id__in=complete_set_ids)
        )
        valid_sets = [
            cs for cs in locked_sets if cs.order_id is None and not cs.saved_for_later
        ]
        if len(valid_sets) != len(complete_set_ids):
            return Response(
                {'error': 'One or more complete sets are invalid or already attached to an order'},
                status=status.HTTP_400_BAD_REQUEST)

        # Create guest address (customer=None)
        addr = Address.objects.create(
            customer=None,
            full_name=address_data['full_name'].strip(),
            phone=address_data['phone'].strip(),
            address=address_data['address'].strip(),
            city=address_data['city'].strip(),
            province_state=address_data['province_state'].strip(),
            country=address_data['country'].strip(),
            post_code=address_data['post_code'].strip(),
        )

        # Create OrderInfo with customer=None
        try:
            order = OrderInfo(
                customer=None,
                email=email,
                order_number=generate_order_number(),
                order_status='PROCESSING',
                payment_status='UNPAID',
                payment_type='paypal',
                address=addr,
                shipping_company=shipping_method,
                comment='',
                refound_status='',
                refound_amount=0,
                sub_total=0,
                shipping_cost=0,
                total_amount=0,
            )
            order.save()
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Link complete sets
        CompleteSet.objects.filter(id__in=complete_set_ids).update(order=order)

        # Calculate totals
        order.sub_total = OrderService.calculate_sub_total(order)
        order.shipping_cost = OrderService.calculate_shipping_cost(
            country, float(order.sub_total), shipping_method)
        order.total_amount = order.sub_total + order.shipping_cost

        OrderInfo.objects.filter(pk=order.pk).update(
            sub_total=order.sub_total,
            shipping_cost=order.shipping_cost,
            total_amount=order.total_amount,
        )

    # Track in session for ownership
    request.session['guest_pending_order_id'] = order.pk

    return Response({
        'order_id':         order.pk,
        'order_number':     order.order_number,
        'sub_total':        str(order.sub_total),
        'shipping_cost':    str(order.shipping_cost),
        'total_before_tax': str(order.total_amount),
    }, status=status.HTTP_201_CREATED)


# ── Guest payment confirmation ────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def confirmPaymentGuest(request):
    """
    Record a completed PayPal payment for a guest order and mark it PAID.
    Ownership validated via session (guest_pending_order_id); the payment
    itself is validated against PayPal's own servers (see confirmPayment).
    """
    data             = request.data
    order_id         = data.get('order_id')
    paypal_order_id  = data.get('paypal_order_id', '')

    if not order_id:
        return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not paypal_order_id:
        return Response({'error': 'paypal_order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Session-based ownership check
    session_order_id = request.session.get('guest_pending_order_id')
    if session_order_id != order_id:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        try:
            order = OrderInfo.objects.select_for_update().get(
                pk=order_id, customer=None)
        except OrderInfo.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == 'PAID':
            return Response({'error': 'Order is already paid'}, status=status.HTTP_400_BAD_REQUEST)

        if OrderPayment.objects.filter(gateway_transaction_id=paypal_order_id).exists():
            return Response({'error': 'This PayPal payment has already been used'},
                             status=status.HTTP_400_BAD_REQUEST)

        capture_id, captured_amount, result = _verify_and_extract_capture(
            paypal_order_id, order.total_amount)
        if capture_id is None:
            return Response({'error': result}, status=status.HTTP_400_BAD_REQUEST)
        payer_email = result

        OrderPayment.objects.create(
            transaction_id=capture_id,
            order=order,
            payment_gateway='paypal',
            transaction_amount=str(captured_amount),
            payer_email=payer_email,
            gateway_transaction_id=paypal_order_id,
            payment_response=data.get('payment_response', {}),
            transaction_status='completed',
        )

        OrderInfo.objects.filter(pk=order.pk).update(
            payment_status='PAID',
            payment_type='paypal',
        )

    # Remove paid items from guest cart
    from Customer.models import ShoppingCart as ShoppingCartModel
    paid_set_ids = list(CompleteSet.objects.filter(order=order).values_list('id', flat=True))
    if paid_set_ids:
        for cart in ShoppingCartModel.objects.filter(eyeglasses_set__id__in=paid_set_ids).distinct():
            cart.eyeglasses_set.remove(*paid_set_ids)

    # Clean up session
    request.session.pop('guest_pending_order_id', None)
    request.session.pop('guest_cart_id', None)
    request.session['guest_completed_order'] = {
        'order_number': order.order_number,
        'email': order.email,
    }

    # Send order confirmation email
    import logging
    _logger = logging.getLogger(__name__)
    email_sent = False
    email_error = None
    try:
        order.refresh_from_db()
        _logger.info(
            'Guest order email debug: order=%s email=%r customer=%r',
            order.order_number, order.email, order.customer_id,
        )
        from Order.email_service import send_order_confirmation
        send_order_confirmation(order)
        email_sent = True
    except Exception as exc:
        email_error = str(exc)
        _logger.exception(
            'Failed to send order confirmation email for guest order %s', order.order_number)

    return Response(
        {
            'success': True,
            'order_number': order.order_number,
            'email_sent': email_sent,
            'email_error': email_error,
        },
        status=status.HTTP_200_OK)


# ── Guest cancel pending order ────────────────────────────────────────────────

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def cancelPendingOrderGuest(request, order_id):
    """Cancel a guest's pending (UNPAID) order. Session-based ownership."""
    session_order_id = request.session.get('guest_pending_order_id')
    if session_order_id != order_id:
        return Response({'error': 'Pending order not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        order = OrderInfo.objects.get(pk=order_id, payment_status='UNPAID', customer=None)
    except OrderInfo.DoesNotExist:
        return Response({'error': 'Pending order not found'}, status=status.HTTP_404_NOT_FOUND)

    _cancel_orders(OrderInfo.objects.filter(pk=order.pk))
    request.session.pop('guest_pending_order_id', None)

    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Guest order lookup ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def guestOrderLookup(request):
    """
    Look up a guest order by email + order_number.
    Returns limited order info (no sensitive data).
    """
    from django.core.cache import cache

    email = request.query_params.get('email', '').strip().lower()
    order_number = request.query_params.get('order_number', '').strip()

    if not email or not order_number:
        return Response({'error': 'email and order_number are required'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Rate limit by IP
    ip = request.META.get('REMOTE_ADDR', 'unknown')
    rl_key = f'rl:guest_lookup:{ip}'
    count = cache.get(rl_key, 0)
    if count >= 10:
        return Response({'error': 'Too many attempts. Please try again later.'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    cache.set(rl_key, count + 1, 300)

    try:
        order = OrderInfo.objects.get(
            order_number=order_number, email__iexact=email, customer=None)
    except OrderInfo.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'order_number':   order.order_number,
        'order_status':   order.order_status,
        'payment_status': order.payment_status,
        'created_at':     order.created_at.isoformat(),
        'shipping_company': order.shipping_company,
    })
