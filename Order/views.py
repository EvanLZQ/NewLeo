import uuid
import datetime

from django.conf import settings
from django.shortcuts import redirect
from rest_framework.response import Response
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
import paypalrestsdk

from .models import *
from .serializer import CompleteSetSerializer, OrderSerializer, CompleteSetObjectSerializer
from .service.order_service import OrderService

paypalrestsdk.configure({
    "mode": settings.PAYPAL_MODE,
    "client_id": settings.PAYPAL_CLIENT_ID,
    "client_secret": settings.PAYPAL_CLIENT_SECRET,
})

# Create your views here.


@api_view(['GET'])
def getCompleteSet(request):
    set = CompleteSet.objects.all()
    serializer = CompleteSetSerializer(set, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
def deleteCompleteSet(request, set_id):
    set = CompleteSet.objects.get(id=set_id)
    set.delete()
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
def getTargetCompleteSet(request, set_id):
    set = CompleteSet.objects.get(id=set_id)
    serializer = CompleteSetSerializer(set, many=False)
    return Response(serializer.data)


@api_view(['PATCH'])
def updateCompleteSet(request, set_id):
    try:
        set = CompleteSet.objects.get(id=set_id)
    except CompleteSet.DoesNotExist:
        return Response({'error': 'Complete Set not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = CompleteSetSerializer(
        instance=set, data=request.data, partial=True, context={'request': request}
    )
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def getAllOrders(request):
    orders = OrderInfo.objects.all()
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getTargetOrder(request, id):
    order = OrderInfo.objects.get(id=id)
    serializer = OrderSerializer(order)
    return Response(serializer.data)


@api_view(['GET'])
def getCompleteSetLoader(request, set_id):
    set = CompleteSet.objects.get(id=set_id)
    serializer = CompleteSetObjectSerializer(set, many=False)
    return Response(serializer.data)


# ── Order helpers ─────────────────────────────────────────────────────────────

def generate_order_number():
    """Produce a unique order number like ELW-20260226-A3F7B1."""
    today = datetime.datetime.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"ELW-{today}-{suffix}"


@api_view(['POST'])
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
    # Always prefer the authenticated user's e-mail over whatever the client sends
    if getattr(request.user, 'is_authenticated', False):
        email = getattr(request.user, 'email', None) or email

    if not complete_set_ids:
        return Response(
            {'error': 'complete_set_ids is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Step 0a: item-based cleanup (runs BEFORE validation) ─────────────────
    # Cancel any UNPAID orders that currently own the requested items,
    # regardless of who created them.  This recovers items stuck because of:
    #   • Orders created before customer= FK was added  (customer=NULL)
    #   • Frontend cancel failures  (network error, page refresh, tab close)
    # ALL CompleteSet rows on those orders are freed — not just the requested
    # ones — so the order is left in a consistent state before deletion.
    stuck_orders = OrderInfo.objects.filter(
        completeset__id__in=complete_set_ids,
        payment_status='UNPAID',
    ).distinct()
    if stuck_orders.exists():
        CompleteSet.objects.filter(order__in=stuck_orders).update(order=None)
        stuck_orders.delete()

    # ── Step 0b: user-based cleanup ───────────────────────────────────────────
    # Cancel any remaining stale UNPAID orders for this authenticated user
    # that don't own these specific items (e.g. orders from another device).
    is_authenticated = getattr(request.user, 'is_authenticated', False)
    if is_authenticated:
        stale = OrderInfo.objects.filter(
            customer=request.user,
            payment_status='UNPAID',
        )
        if stale.exists():
            CompleteSet.objects.filter(order__in=stale).update(order=None)
            stale.delete()

    # ── Validate (after cleanup so freed items now pass) ──────────────────────
    # Only fails here for genuinely bad input: non-existent IDs, wrong user's
    # items, or items the user intentionally marked as saved-for-later.
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

    # ── Step 1: create the OrderInfo shell ───────────────────────────────────
    # Supply placeholder totals (0); overwritten with real values in step 3.
    try:
        order = OrderInfo(
            customer=request.user if is_authenticated else None,
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
        order.save()   # triggers update_order_totals → 0 totals (no sets yet)
    except Exception as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # ── Step 2: link the complete sets ───────────────────────────────────────
    CompleteSet.objects.filter(id__in=complete_set_ids).update(order=order)

    # ── Step 3: calculate totals using country + method from the request ──────
    # AddressForm collects address fields locally without saving them to the DB,
    # so order.address is null.  We use the country from the request body directly
    # to avoid that dependency.
    order.sub_total     = OrderService.calculate_sub_total(order)
    order.shipping_cost = OrderService.calculate_shipping_cost(
        country, float(order.sub_total), shipping_method,
    )
    order.total_amount  = order.sub_total + order.shipping_cost

    # Persist via QuerySet.update() to bypass the save() hook
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
            'total_before_tax': str(order.total_amount),  # sub_total + shipping
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
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

    try:
        order = OrderInfo.objects.get(pk=order_id)
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

    # Mark the order PAID — bypass save() to avoid re-running update_order_totals
    OrderInfo.objects.filter(pk=order.pk).update(
        payment_status='PAID',
        payment_type='paypal',
    )

    return Response(
        {'success': True, 'order_number': order.order_number},
        status=status.HTTP_200_OK,
    )


@api_view(['DELETE'])
def cancelPendingOrder(request, order_id):
    """
    Cancel a pending (UNPAID) order created by createPendingOrder.

    Unlinks the attached CompleteSet objects (so they return to the cart) and
    deletes the OrderInfo record.  Used when the user goes back from the Payment
    step to avoid accumulating stale UNPAID orders.
    """
    try:
        order = OrderInfo.objects.get(pk=order_id, payment_status='UNPAID')
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
                # Convert to str to avoid Google App Engine Unicode issue
                # https://github.com/paypal/rest-api-sdk-python/pull/58
                approval_url = str(link.href)
                # return JsonResponse({'approval_url': approval_url})
                print("Redirect for approval: %s" % (approval_url))
                return redirect(approval_url)
    else:
        print(payment.error)
        return JsonResponse({'error': 'payment not created'})
