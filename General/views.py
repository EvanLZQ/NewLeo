from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import CurrencyConversion
from .serializer import CurrencySerializer

# Create your views here.


@api_view(['GET'])
def getCurrencyConversion(request):
    currency = CurrencyConversion.objects.all()
    serializer = CurrencySerializer(currency, many=True)
    return Response(serializer.data)
