from django.conf import settings
from django.shortcuts import redirect
from rest_framework.response import Response
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
import paypalrestsdk

from .models import *
from .serializer import CompleteSetSerializer, OrderSerializer, CompleteSetObjectSerializer

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


# PayPal View
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
