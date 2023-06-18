from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import *
from .serializer import ProductSerializer, ProductDimensionSerializer


@api_view(['GET'])
def getProducts(request):
    products = ProductInfo.objects.select_related(
        'dimensionID').filter(online=True)
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getProduct(request, sku):
    products = ProductInfo.objects.select_related(
        'dimensionID').get(sku=sku)
    serializer = ProductSerializer(products, many=False)
    return Response(serializer.data)
