from django.shortcuts import render
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .serializer import CustomerSerializer, ShoppingListSerializer
from .models import ShoppingList
from rest_framework import status

# Create your views here.

User = get_user_model()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user(request):
    user = request.user
    serializer = CustomerSerializer(user)
    return Response(serializer.data)


@api_view(['GET'])
def get_shopping_list(request, list_id):
    shopping_list = ShoppingList.objects.get(id=list_id)
    serializer = ShoppingListSerializer(shopping_list)
    return Response(serializer.data)


@api_view(['POST'])
def create_shopping_list(request):
    serializer = ShoppingListSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
def update_shopping_list(request, list_id):
    try:
        shopping_list = ShoppingList.objects.get(id=list_id)
    except ShoppingList.DoesNotExist:
        return Response({'error': 'ShoppingList not found'}, status=status.HTTP_404_NOT_FOUND)

    # Deserialize and validate the request data
    # `partial=True` allows for partial updates
    serializer = ShoppingListSerializer(
        instance=shopping_list, data=request.data, partial=True)

    if serializer.is_valid():
        # Save the updated ShoppingList object
        print("Here")
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        print("Here")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
