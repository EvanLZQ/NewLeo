from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

from .models import *
from .serializer import CompleteSetSerializer


# Create your views here.

@api_view(['GET'])
def getCompleteSet(request):
    set = CompleteSet.objects.all()
    serializer = CompleteSetSerializer(set, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def createCompleteSet(request):
    if request.method == 'POST':
        serializer = CompleteSetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
