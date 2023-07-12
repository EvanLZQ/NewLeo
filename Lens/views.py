from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import *
from .serializer import *

# Create your views here.


@api_view(["GET"])
def getLensUsage(request):
    usage = LensUsage.objects.all()
    serializer = LensUsageSerializer(usage, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getLensColor(request):
    color = LensColor.objects.all()
    serializer = LensColorSerializer(color, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getLensDensity(request):
    density = LensDensity.objects.all()
    serializer = LensDensitySerializer(density, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getLensCoating(request):
    coating = LensCoating.objects.all()
    serializer = LensCoatingSerializer(coating, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def getLensIndex(request):
    index = LensIndex.objects.all()
    serializer = LensIndexSerializer(index, many=True)
    return Response(serializer.data)
