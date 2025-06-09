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


@api_view(['POST'])
def createCompleteSet(request):
    if request.method == 'POST':
        serializer = CompleteSetSerializer(
            data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
