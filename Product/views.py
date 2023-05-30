from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import *
from .serializer import ProductSerializer, ProductDimensionSerializer

# Create your views here.


def all_products(request):
    products = ProductInfo.objects.select_related(
        'productimage', 'productdimension', 'productcolor').filter(online=True)


@api_view(['GET'])
def getProducts(request):
    products = ProductInfo.objects.select_related('dimensionID').all()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


# @api_view(['GET'])
# def getProductDimension(request):
#     productDimension = ProductDimension.objects.all()
#     serializer = ProductDimensionSerializer(productDimension, many=True)
#     return Response(serializer.data)
