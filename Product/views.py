from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import *
from .serializer import ProductInstanceSerializer, ProductSerializer, TargetInstanceSerializer


@api_view(['GET'])
def getProducts(request):
    products = ProductInfo.objects.filter(
        productInstance__isnull=False).distinct()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getProduct(request, sku):
    product_instance = ProductInstance.objects.get(sku=sku)
    serializer = ProductInstanceSerializer(product_instance)
    # product_id = ProductInstance.objects.get(sku=sku).product.id
    # product = ProductInfo.objects.get(id=product_id)
    # serializer = TargetInstanceSerializer(
    #     product, many=False, context={'sku': sku})
    return Response(serializer.data)


@api_view(['GET'])
def getModel(request, model):
    product = ProductInfo.objects.get(model_number=model)
    serialier = ProductSerializer(product, many=False)
    return Response(serialier.data)
