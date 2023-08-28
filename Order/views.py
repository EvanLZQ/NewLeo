from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

from .models import *
from .serializer import CompleteSetSerializer, OrderSerializer


# Create your views here.

@api_view(['GET'])
def getCompleteSet(request):
    set = CompleteSet.objects.all()
    serializer = CompleteSetSerializer(set, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def createCompleteSet(request):
    if request.method == 'POST':
        serializer = CompleteSetSerializer(data=request.data)
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
        instance=set, data=request.data, partial=True)
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
