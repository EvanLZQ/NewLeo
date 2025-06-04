from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import PrescriptionInfo
from .serializer import PrescriptionSerializer


@api_view(['GET', 'POST'])
def prescription_list_create(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            prescriptions = PrescriptionInfo.objects.filter(
                customer__user=request.user)
        else:
            prescriptions = PrescriptionInfo.objects.none()
        serializer = PrescriptionSerializer(prescriptions, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = PrescriptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
def prescription_detail(request, pk):
    try:
        prescription = PrescriptionInfo.objects.get(pk=pk)
    except PrescriptionInfo.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = PrescriptionSerializer(prescription)
        return Response(serializer.data)

    elif request.method == 'PATCH':
        serializer = PrescriptionSerializer(
            prescription, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        prescription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
