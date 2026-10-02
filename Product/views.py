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
    products = (
        ProductInfo.objects.filter(
            Q(productInstance__isnull=False) & Q(productInstance__online=True)
        )
        # 外键
        .select_related('supplier')
        # 一对多 / 多对多
        .prefetch_related(
            'productInstance__color_img',     # 实例的颜色图
            'productInstance__productImage',  # 实例下的所有图片
            'productReview',                  # 产品评论
            'productTag'                      # 产品标签 (M2M)
        )
        .distinct()
    )
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getPageProducts(request):
    # 从前端 query string 获取可选参数
    exclude = request.GET.get('exclude', None)   # 需要排除的型号
    tag = request.GET.get('tag', None)           # 标签筛选

    # 基础查询：只取有实例（productInstance）且实例标记为 online 的产品
    products = (
        ProductInfo.objects.filter(
            Q(productInstance__isnull=False) & Q(productInstance__online=True)
        )
        # select_related：用于一对一/多对一关系（例如 supplier），避免 N+1 查询
        .select_related('supplier')
        # prefetch_related：用于一对多/多对多关系，提前把相关数据取出来，避免序列化时反复查数据库
        .prefetch_related(
            'productInstance__color_img',     # ProductInstance → ProductColorImg
            'productInstance__productImage',  # ProductInstance → ProductImage
            'productReview',                  # ProductInfo → ProductReview
            'productTag'                      # ProductInfo → ProductTag (M2M)
        )
        .distinct()  # 防止因多对多或连接关系导致重复数据
    )

    # 按需排除某个型号
    if exclude:
        products = products.exclude(model_number=exclude)

    # 按需筛选标签
    if tag:
        products = products.filter(productTag__name=tag)

    # 获取分页大小（默认 8 个产品）
    number_of_page = request.GET.get('number', 8)
    try:
        number_of_page = int(number_of_page)
        if number_of_page <= 0:
            number_of_page = 8
    except ValueError:
        number_of_page = 8

    # 创建分页器
    paginator = Paginator(products, number_of_page)

    # 获取当前页码（默认为第 1 页）
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1

    # 如果页码超出范围，则返回空结果
    if page_number > paginator.num_pages or page_number < 1:
        return Response({
            'results': [],
            'total_count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_number,
        })

    # 获取对应页的数据
    page_obj = paginator.get_page(page_number)

    # 序列化分页结果
    serializer = ProductSerializer(page_obj, many=True)

    return Response({
        'results': serializer.data,
        'total_count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_number,
    })


@api_view(['GET'])
def getProduct(request, sku):
    try:
        product_instance = ProductInstance.objects.get(sku=sku)
    except ProductInstance.DoesNotExist:
        return Response({'error': 'Product not found'}, status=404)
    serializer = ProductInstanceSerializer(product_instance)
    return Response(serializer.data)


@api_view(['GET'])
def getModel(request, model):
    try:
        product = ProductInfo.objects.get(model_number=model)
    except ProductInfo.DoesNotExist:
        return Response({'error': 'Product not found'}, status=404)
    serializer = ProductSerializer(product, many=False)
    return Response(serializer.data)


@api_view(['GET'])
def getModelUsingSku(request, sku):
    try:
        product_instance = ProductInstance.objects.get(sku=sku)
        product = ProductInfo.objects.get(id=product_instance.product_id)
    except (ProductInstance.DoesNotExist, ProductInfo.DoesNotExist):
        return Response({'error': 'Product not found'}, status=404)
    serializer = SKUtoModelSerializer(product, many=False)
    return Response(serializer.data)


@api_view(['GET'])
def filterProduct(request):
    products = (
        ProductInfo.objects.filter(
            Q(productInstance__isnull=False) & Q(productInstance__online=True)
        )
        .select_related('supplier')
        .prefetch_related(
            'productInstance__color_img',
            'productInstance__productImage',
            'productReview',
            'productTag'
        )
        .distinct()
    )

    filter_object = request.query_params.get('filter', None)
    if filter_object:
        import json
        try:
            filter_dict = json.loads(filter_object)
        except (json.JSONDecodeError, ValueError):
            return Response({'error': 'Invalid filter format'}, status=400)

        # Every dimension below is applied as its OWN .filter() call, not
        # folded into one big combined Q. Tag-based dimensions (Shape,
        # Material, Usage, Occasion, Collection) all match through the same
        # multi-valued productTag relation — within a single .filter()
        # call Django requires every condition on a multi-valued relation
        # to be satisfied by the *same* related row, so one combined Q
        # asked for a single tag that is simultaneously, say, "Round" and
        # "Metal(Alloy)" — impossible, so any two tag facets together
        # always returned 0 results (verified live: Shape=Round 7,
        # Material=Metal(Alloy) 9, both together 0). Separate .filter()
        # calls each get their own join, so facets AND across dimensions
        # (and OR within one dimension, via __in) the way the UI implies.
        colors = filter_dict.get('Color', [])
        if colors:
            products = products.filter(productInstance__color_display_name__in=colors)

        genders = filter_dict.get('Gender', [])
        if genders:
            products = products.filter(gender__in=genders)

        sizes = filter_dict.get('Size', [])
        if sizes:
            products = products.filter(letter_size__in=sizes)

        rims = filter_dict.get('Rim', [])
        if rims:
            products = products.filter(frame_style__in=rims)

        search = filter_dict.get('Search', None)
        if search:
            products = products.filter(
                Q(name__icontains=search) | Q(model_number__icontains=search))

        for key in ('Shape', 'Material', 'Occasion', 'Collection'):
            values = filter_dict.get(key, [])
            if values:
                products = products.filter(productTag__name__in=values)

        # Usage (Sunglasses/Driving/Reading/Progressive/Photochromic/...)
        # is matched against tags in the "Usage" category only — a
        # same-named tag in another category (e.g. a Collection called
        # "Reading") must not make a frame show up under Usage. Both
        # conditions sit in one .filter() on purpose here: they have to
        # hold on the same tag row.
        usages = filter_dict.get('Usage', [])
        if usages:
            products = products.filter(
                productTag__category='Usage', productTag__name__in=usages)

        # Matches by ProductPromotion.slug — e.g. "buy_one_get_one_free".
        # Separate from tags: promotions are their own model, attached to
        # ProductInstance (not ProductInfo) via a M2M.
        promotions = filter_dict.get('Promotion', [])
        if promotions:
            products = products.filter(
                productInstance__productPromotion__slug__in=promotions,
                productInstance__productPromotion__is_active=True,
            )

        products = products.distinct()

    # Pagination
    number_of_page = request.GET.get('number', 30)
    try:
        number_of_page = int(number_of_page)
        if number_of_page <= 0:
            number_of_page = 30
    except ValueError:
        number_of_page = 30

    paginator = Paginator(products, number_of_page)

    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1

    if page_number < 1:
        page_number = 1
    if page_number > paginator.num_pages:
        page_number = paginator.num_pages

    page_obj = paginator.get_page(page_number)
    serializer = ProductSerializer(page_obj, many=True)

    return Response({
        'results': serializer.data,
        'total_count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_number,
    })


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
