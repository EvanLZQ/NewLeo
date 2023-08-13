from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from .serializer import CustomerSerializer, ShoppingListSerializer
from .models import ShoppingList
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from Leoptique.authentication import AccessTokenAuthentication
from google.oauth2 import id_token
from django.utils import timezone
import datetime
from .models import CustomerInfo
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework.permissions import AllowAny
from google.auth.transport import requests
import uuid
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.backends import ModelBackend

# Create your views here.

User = get_user_model()


@csrf_exempt
@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_user(request):
    user = request.user
    serializer = CustomerSerializer(user)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def is_authenticated(request):
    return Response(status=status.HTTP_200_OK)


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


@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return Response({"message": "Login successful!"})
    else:
        return Response({"error": "Invalid credentials"}, status=400)


@api_view(['POST'])
def logout_view(request):
    logout(request)
    return Response({"message": "Logged out successfully!"})


@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    credential = request.data.get('credential')
    client_id = request.data.get('clientId')

    # Verify the token
    try:
        id_info = id_token.verify_oauth2_token(
            credential, requests.Request(), client_id)
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
    except ValueError:
        return Response({'error': 'Invalid token'}, status=400)

    # Get or create user
    # Extract the relevant fields from id_info
    family_name = id_info.get('family_name', '')
    given_name = id_info.get('given_name', '')
    email = id_info.get('email', '')
    picture = id_info.get('picture', '')

    # Get or create user
    user, created = CustomerInfo.objects.get_or_create(
        username=email,
        defaults={
            'first_name': given_name,
            'last_name': family_name,
            'icon_url': picture
        }
    )

    # If the user already exists, update their details
    if not created:
        user.first_name = given_name
        user.last_name = family_name
        user.icon_url = picture
        user.save()

    # application = Application.objects.get(
    #     client_id="l5cAOrriN5gIvTiLjOENupQsp6ppISdp1iYyU8iu")

    # generated_token = str(uuid.uuid4())
    # # Generate access token
    # token = AccessToken.objects.create(
    #     user=user,
    #     token=generated_token,
    #     application=application,
    #     expires=timezone.now() + datetime.timedelta(days=1)
    # )

    # refresh_token = RefreshToken.objects.create(
    #     user=user,
    #     token=str(uuid.uuid4()),
    #     access_token=token,
    #     application=application
    # )

    user.backend = 'django.contrib.auth.backends.ModelBackend'

    login(request, user)

    user_brief = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": email,
        "phone": user.phone,
        "gender": user.gender,
        "icon_url": user.icon_url,
    }

    # return Response({'token': token.token, 'refresh_token': refresh_token.token})
    # response = Response(user_brief, status=200)

    # Set the tokens as cookies
    # response.set_cookie('access_token', token.token,
    #                     max_age=3600 * 24, samesite='Lax', domain='localhost')  # 1 day
    # response.set_cookie('refresh_token', refresh_token.token,
    #                     max_age=3600 * 24 * 30, samesite='Lax', domain='localhost')  # 30 days

    return Response(user_brief, status=200)
