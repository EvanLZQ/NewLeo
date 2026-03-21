import uuid
import datetime

from django.conf import settings
from django.db import transaction
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


def generate_order_number():
    """Produce a unique order number like ELW-20260226-A3F7B1."""
    today = datetime.datetime.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"ELW-{today}-{suffix}"


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
    # Authenticated user: check user ownership
    if request.user and request.user.is_authenticated:
        if not _user_owns_complete_set(request.user, set_id):
            return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Guest: check if the set is in their session cart or has no order (just created)
        from Customer.models import ShoppingCart as ShoppingCartModel
        guest_cart_id = request.session.get('guest_cart_id')
        in_guest_cart = False
        if guest_cart_id:
            in_guest_cart = ShoppingCartModel.objects.filter(
                pk=guest_cart_id, eyeglasses_set__id=set_id).exists()
        # Also allow deleting unattached sets (just created, not in any cart/order yet)
        is_unattached = CompleteSet.objects.filter(id=set_id, order=None).exists()
        if not in_guest_cart and not is_unattached:
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

    # ── Lens options (skip null FKs — e.g. color is null for Clear type) ────
    for component, option_obj in [
        ('usage',   instance.usage),
        ('color',   instance.color),
        ('coating', instance.coating),
        ('index',   instance.index),
    ]:
        if option_obj is None:
            continue
        backend_p  = float(option_obj.add_on_price)
        frontend_p = float(snapshot.get(component) or 0)
        breakdown.append({
            'component':      component,
            'label':          option_obj.name,
            'option_type':    option_obj.option_type,
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
@permission_classes([IsAuthenticated])
def getTargetCompleteSet(request, set_id):
    if not _user_owns_complete_set(request.user, set_id):
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        complete_set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CompleteSetSerializer(complete_set, many=False)
    return Response(serializer.data)


@api_view(['PATCH'])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated])
def updateCompleteSet(request, set_id):
    if not _user_owns_complete_set(request.user, set_id):
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
@permission_classes([IsAuthenticated])
def getCompleteSetLoader(request, set_id):
    if not _user_owns_complete_set(request.user, set_id):
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

    with transaction.atomic():
        # ── Step 0a: item-based cleanup (runs BEFORE validation) ─────────────
        # Cancel any UNPAID orders that currently own the requested items,
        # regardless of who created them.  This recovers items stuck because of:
        #   • Orders created before customer= FK was added  (customer=NULL)
        #   • Frontend cancel failures  (network error, page refresh, tab close)
        # ALL CompleteSet rows on those orders are freed — not just the requested
        # ones — so the order is left in a consistent state before deletion.
        # Materialise PKs first — Django forbids .delete() on a .distinct() queryset.
        stuck_order_ids = list(
            OrderInfo.objects.filter(
                completeset__id__in=complete_set_ids,
                payment_status='UNPAID',
            ).distinct().values_list('pk', flat=True)
        )
        if stuck_order_ids:
            CompleteSet.objects.filter(order_id__in=stuck_order_ids).update(order=None)
            OrderInfo.objects.filter(pk__in=stuck_order_ids).delete()

        # ── Step 0b: user-based cleanup ─────────────────────────────────────────
        # Cancel any remaining stale UNPAID orders for this authenticated user
        # that don't own these specific items (e.g. orders from another device).
        stale = OrderInfo.objects.filter(
            customer=request.user,
            payment_status='UNPAID',
        )
        if stale.exists():
            CompleteSet.objects.filter(order__in=stale).update(order=None)
            stale.delete()

        # ── Validate (after cleanup so freed items now pass) ────────────────────
        valid_sets = CompleteSet.objects.filter(
            id__in=complete_set_ids,
            order=None,
            saved_for_later=False,
        )
        if valid_sets.count() != len(complete_set_ids):
            return Response(
                {'error': 'One or more complete sets are invalid or already attached to an order'},
                status=status.HTTP_400_BAD_REQUEST,
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
                address_id=address_id,
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
        order_id               – int    our internal OrderInfo PK
        paypal_transaction_id  – str    PayPal capture / transaction ID
        payer_email            – str    PayPal payer e-mail
        transaction_amount     – str    amount actually charged (decimal string)
        payment_response       – dict   full PayPal capture response (stored for audit)

    Response (200):
        { success: true, order_number }
    """
    data                  = request.data
    order_id              = data.get('order_id')
    paypal_transaction_id = data.get('paypal_transaction_id', '')
    payer_email           = data.get('payer_email', '')
    transaction_amount    = data.get('transaction_amount', '0')
    payment_response      = data.get('payment_response', {})

    if not order_id:
        return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        try:
            order = OrderInfo.objects.select_for_update().get(
                pk=order_id, customer=request.user)
        except OrderInfo.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == 'PAID':
            return Response({'error': 'Order is already paid'}, status=status.HTTP_400_BAD_REQUEST)

        # Create the payment record
        OrderPayment.objects.create(
            transaction_id=paypal_transaction_id,
            order=order,
            payment_gateway='paypal',
            transaction_amount=transaction_amount,
            payer_email=payer_email,
            gateway_transaction_id=paypal_transaction_id,
            payment_response=payment_response,
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
    deletes the OrderInfo record.  Used when the user goes back from the Payment
    step to avoid accumulating stale UNPAID orders.
    """
    try:
        order = OrderInfo.objects.get(
            pk=order_id, payment_status='UNPAID', customer=request.user)
    except OrderInfo.DoesNotExist:
        return Response({'error': 'Pending order not found'}, status=status.HTTP_404_NOT_FOUND)

    # Return items to the cart (order FK → None) before deleting the order
    CompleteSet.objects.filter(order=order).update(order=None)
    order.delete()

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
        if cs_id:
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

    with transaction.atomic():
        # Step 0a: item-based cleanup — same as authenticated
        stuck_order_ids = list(
            OrderInfo.objects.filter(
                completeset__id__in=complete_set_ids,
                payment_status='UNPAID',
            ).distinct().values_list('pk', flat=True)
        )
        if stuck_order_ids:
            CompleteSet.objects.filter(order_id__in=stuck_order_ids).update(order=None)
            OrderInfo.objects.filter(pk__in=stuck_order_ids).delete()

        # Step 0b: session-based cleanup — cancel previous guest pending order
        prev_order_id = request.session.get('guest_pending_order_id')
        if prev_order_id:
            stale = OrderInfo.objects.filter(pk=prev_order_id, payment_status='UNPAID')
            if stale.exists():
                CompleteSet.objects.filter(order__in=stale).update(order=None)
                stale.delete()

        # Validate
        valid_sets = CompleteSet.objects.filter(
            id__in=complete_set_ids, order=None, saved_for_later=False)
        if valid_sets.count() != len(complete_set_ids):
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
    Ownership validated via session (guest_pending_order_id).
    """
    data                  = request.data
    order_id              = data.get('order_id')
    paypal_transaction_id = data.get('paypal_transaction_id', '')
    payer_email           = data.get('payer_email', '')
    transaction_amount    = data.get('transaction_amount', '0')
    payment_response      = data.get('payment_response', {})

    if not order_id:
        return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

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

        OrderPayment.objects.create(
            transaction_id=paypal_transaction_id,
            order=order,
            payment_gateway='paypal',
            transaction_amount=transaction_amount,
            payer_email=payer_email,
            gateway_transaction_id=paypal_transaction_id,
            payment_response=payment_response,
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
    try:
        order.refresh_from_db()
        from Order.email_service import send_order_confirmation
        send_order_confirmation(order)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send order confirmation email for guest order %s', order.order_number)

    return Response(
        {'success': True, 'order_number': order.order_number},
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

    CompleteSet.objects.filter(order=order).update(order=None)
    order.delete()
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
