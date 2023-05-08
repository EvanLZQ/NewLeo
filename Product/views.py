from django.shortcuts import render

from .models import *

# Create your views here.


def all_products(request):
    products = ProductInfo.objects.select_related(
        'productimage', 'productdimension', 'productcolor').filter(online=True)
