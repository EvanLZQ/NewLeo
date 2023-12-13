from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.db.models import Q
from django.core.paginator import Paginator
import logging

from .models import *
from .serializer import *


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
        products = products.filter(productTag__name=tag)
    number_of_page = request.GET.get('number', 6)
    paginator = Paginator(products, number_of_page)
    page_number = int(request.GET.get('page', 1))
    if page_number > paginator.num_pages or page_number < 1:
        return Response([])
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
    product = ProductInfo.objects.get(id=product_id)
    serializer = SKUtoModelSerializer(product, many=False)
    return Response(serializer.data)


@api_view(['GET'])
def filterProduct(request):
    products = ProductInfo.objects.filter(
        productInstance__isnull=False).distinct()

    filter_object = request.query_params.get('filter', None)
    if filter_object:
        import json
        filter_dict = json.loads(filter_object)

        # Build the Q object for colors
        colors = filter_dict.get('Color', [])
        color_q_objects = Q()
        for color in colors:
            color_q_objects |= Q(productInstance__color_display_name=color)

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

        # Build the Q object for Rim
        rims = filter_dict.get('Rim', [])
        rim_q_objects = Q()
        for rim in rims:
            rim_q_objects |= Q(frame_style=rim)

        # Build the Q object for tags
        shape = filter_dict.get('Shape', [])
        material = filter_dict.get('Material', [])
        tags = shape + material
        tag_q_objects = Q()
        for tag in tags:
            tag_q_objects |= Q(productTag__name=tag)

        # Combine search results
        combined_q_objects = color_q_objects & gender_q_objects & size_q_objects & rim_q_objects & tag_q_objects
        # Filter search results
        products = products.filter(combined_q_objects).distinct()

    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getProductPromotions(request):
    promotions = ProductPromotion.objects.filter(is_active=True)
    serializer = ProductPromotionSerializer(promotions, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getAllColorNames(request):
    try:
        distinct_colors = ProductInstance.objects.values_list(
            'color_display_name', flat=True).distinct()
        return Response(list(distinct_colors))
    except Exception as e:
        # Log the error and return a meaningful error response
        # Or use logging instead of print
        logging.error(f"Unexpected error: {e}")
        return Response({'error': 'Internal server error'}, status=500)


@api_view(['GET'])
def getAllMaterials(request):
    distinct_materials = ProductTag.objects.filter(category='Material').values_list(
        'name', flat=True).distinct()
    return Response(list(distinct_materials))


@api_view(['GET'])
def getAllShapes(request):
    distinct_shapes = ProductTag.objects.filter(category='Shape').values_list(
        'name', flat=True).distinct()
    return Response(list(distinct_shapes))


@api_view(['GET'])
def getSearchProducts(request):
    search_term = request.GET.get('search', None)
    if search_term:
        products = ProductInfo.objects.filter(
            Q(productInstance__isnull=False) & Q(productInstance__online=True)).distinct()
        products = products.filter(
            Q(model_number__icontains=search_term) | Q(name__icontains=search_term))[:6]
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
    else:
        return Response([])
