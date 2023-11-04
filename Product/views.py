from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.db.models import Q
from django.core.paginator import Paginator

from .models import *
from .serializer import ProductInstanceSerializer, ProductSerializer, SKUtoModelSerializer


@api_view(['GET'])
def getProducts(request):
    products = ProductInfo.objects.filter(
        Q(productInstance__isnull=False) & Q(productInstance__online=True)).distinct()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getPageProducts(request):
    exclude = request.GET.get('exclude', None)
    tag = request.GET.get('tag', None)
    products = ProductInfo.objects.filter(
        Q(productInstance__isnull=False) & Q(productInstance__online=True)).distinct()
    if exclude:
        products = products.exclude(model_number=exclude)
    if tag:
        products = products.filter(producttag__name=tag)
    number_of_page = request.GET.get('number', 6)
    paginator = Paginator(products, number_of_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    serializer = ProductSerializer(page_obj, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getProduct(request, sku):
    product_instance = ProductInstance.objects.get(sku=sku)
    serializer = ProductInstanceSerializer(product_instance)
    return Response(serializer.data)


@api_view(['GET'])
def getModel(request, model):
    product = ProductInfo.objects.get(model_number=model)
    serializer = ProductSerializer(product, many=False)
    return Response(serializer.data)


@api_view(['GET'])
def getModelUsingSku(request, sku):
    product_id = ProductInstance.objects.get(sku=sku).product_id
    print(product_id)
    product = ProductInfo.objects.get(id=product_id)
    serializer = SKUtoModelSerializer(product, many=False)
    return Response(serializer.data)


@api_view(['GET'])
def filterProduct(request):
    products = ProductInfo.objects.filter(
        productInstance__isnull=False).distinct()

    filter_object = request.query_params.get('filter', None)
    if filter_object:
        # Assuming filter_object is a string representation of a dictionary
        import json
        filter_dict = json.loads(filter_object)

        # Build the Q object for colors
        colors = filter_dict.get('Color', [])
        color_q_objects = Q()
        for color in colors:
            color_q_objects |= Q(productInstance__color_base_name=color)

        # Build the Q object for gender
        genders = filter_dict.get('Gender', [])
        gender_q_objects = Q()
        for gender in genders:
            gender_q_objects |= Q(gender=gender)

        # Build the Q object for size
        sizes = filter_dict.get('Size', [])
        size_q_objects = Q()
        for size in sizes:
            size_q_objects |= Q(letter_size=size)

        # Build the Q object for tags
        # tags = filter_dict.get('tags', [])
        # tag_q_objects = Q()
        # for tag in tags:
        #     tag_q_objects |= Q(producttag__slug=tag)

        # Combine search results
        combined_q_objects = color_q_objects & gender_q_objects & size_q_objects
        # Filter search results
        products = products.filter(combined_q_objects).distinct()

    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getProductPromotions(request):
    promotions = ProductPromotion.objects.filter(is_active=True)
    serializer = ProductPromotionSerializer(promotions, many=True)
    return Response(serializer.data)
