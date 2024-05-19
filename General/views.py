from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import CurrencyConversion, FAQ, PageImage
from .serializer import CurrencySerializer, FAQSerializer, PageImageSerializer

# Create your views here.


@api_view(['GET'])
def getCurrencyConversion(request):
    currency = CurrencyConversion.objects.all()
    serializer = CurrencySerializer(currency, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getFAQContents(request):
    faq = FAQ.objects.all()
    serializer = FAQSerializer(faq, many=True)
    return Response(serializer)


@api_view(['GET'])
def getPageImage(request):
    imgPage = request.data.get('page')
    imgSection = request.data.get('section')
    pageImages = PageImage.objects.filter(
        page=imgPage, section=imgSection)
    serializer = PageImageSerializer(pageImages, many=True)
    return Response(serializer.data)
