from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, login, logout
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from General.models import Coupon, Address
from General.serializer import CouponSerializer, ImageSerializer, AddressSerializer
from rest_framework.parsers import MultiPartParser

from Prescription.models import PrescriptionInfo
from Prescription.serializer import PrescriptionSerializer
from .serializer import *
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from Leoptique.authentication import AccessTokenAuthentication
from google.oauth2 import id_token
from django.utils import timezone
import datetime
from .models import CustomerInfo, ShoppingCart, StoreCreditActivity, WishList
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework.permissions import AllowAny
from google.auth.transport import requests
import uuid
from django.views.decorators.csrf import csrf_exempt
from Order.serializer import OrderSerializer
from Order.models import OrderInfo
# from django.contrib.auth.backends import ModelBackend

# Create your views here.

User = get_user_model()


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

# Below is shopping cart views


@api_view(['GET'])
def getShoppingCart(request, cart_id):
    shopping_cart = ShoppingCart.objects.get(id=cart_id)
    serializer = ShoppingCartSerializer(shopping_cart)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getUserShoppingCart(request, cart_id):
    user = request.user
    shopping_cart = user.shopping_cart
    if cart_id:
        # Get the local shopping cart, or return a 404 if not found
        local_cart = get_object_or_404(ShoppingCart, id=cart_id)

        # Merge the local shopping cart into the user's cart
        shopping_cart.merge_with(local_cart)

    serializer = ShoppingCartSerializer(shopping_cart)
    return Response(serializer.data)


@api_view(['POST'])
def createShoppingCart(request):
    serializer = ShoppingCartSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
def updateShoppingCart(request, cart_id):
    try:
        shopping_cart = ShoppingCart.objects.get(id=cart_id)
    except ShoppingCart.DoesNotExist:
        return Response({'error': 'Shopping cart not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ShoppingCartSerializer(
        instance=shopping_cart, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
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


@csrf_exempt
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

    application = Application.objects.get(
        client_id="l5cAOrriN5gIvTiLjOENupQsp6ppISdp1iYyU8iu")

    generated_token = str(uuid.uuid4())
    # Generate access token
    token = AccessToken.objects.create(
        user=user,
        token=generated_token,
        application=application,
        expires=timezone.now() + datetime.timedelta(days=1)
    )

    refresh_token = RefreshToken.objects.create(
        user=user,
        token=str(uuid.uuid4()),
        access_token=token,
        application=application
    )

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
    response = Response(user_brief, status=200)

    # Set the tokens as cookies
    response.set_cookie('access_token', token.token,
                        max_age=3600 * 24, samesite=None, domain='.eyelovewear.com', path='/', httponly=True, secure=True)  # 1 day
    response.set_cookie('refresh_token', refresh_token.token,
                        max_age=3600 * 24 * 30, samesite=None, domain='.eyelovewear.com', path='/', httponly=True, secure=True)  # 30 days
    return response


@api_view(['GET'])
@authentication_classes([AccessTokenAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerProfile(request):
    user = request.user
    serializer = CustomerProfileSerializer(user)
    return Response(serializer.data)


@api_view(['PATCH'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def updateCustomerProfile(request):
    user = request.user
    serializer = CustomerProfileSerializer(
        user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
def createCustomer(request):
    serializer = CustomerCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response("User created successfully", status=201)
    return Response(serializer.errors, status=400)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerOrders(request):
    user = request.user
    orders = OrderInfo.objects.filter(customer=user)
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerStoreCreditActivity(request):
    user = request.user
    activities = StoreCreditActivity.objects.filter(customer=user)
    serializer = StoreCreditActivitySerializer(activities, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerPrescription(request):
    user = request.user
    prescription = PrescriptionInfo.objects.filter(customer=user)
    serializer = PrescriptionSerializer(prescription, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerCoupon(request):
    user = request.user
    coupon = Coupon.objects.filter(online=True, valid_customer=user)
    serializer = CouponSerializer(coupon, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@parser_classes([MultiPartParser])
def uploadCustomerAvatar(request):
    serializer = ImageSerializer(data=request.data)
    if serializer.is_valid():
        image_upload = serializer.save()
        image_url = request.build_absolute_uri(image_upload.image.url)
        return Response({'image_url': image_url}, status=201)
    return Response(serializer.errors, status=400)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def addCustomerPrescription(request):
    user = request.user
    serializer = PrescriptionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(customer=user)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PATCH'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def updateCustomerPrescription(request, prescription_id):
    try:
        prescription = PrescriptionInfo.objects.get(id=prescription_id)
    except PrescriptionInfo.DoesNotExist:
        return Response({'error': 'Prescription not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = PrescriptionSerializer(
        instance=prescription, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerAddress(request):
    user = request.user
    address = Address.objects.filter(customer=user)
    serializer = AddressSerializer(address, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def addCustomerAddress(request):
    user = request.user
    serializer = AddressSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(customer=user)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PATCH'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def updateCustomerAddress(request, address_id):
    try:
        address = Address.objects.get(id=address_id)
    except Address.DoesNotExist:
        return Response({'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = AddressSerializer(
        instance=address, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def deleteCustomerAddress(request, address_id):
    try:
        address = Address.objects.get(id=address_id)
    except Address.DoesNotExist:
        return Response({'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)

    address.delete()
    return Response(status=204)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getUserWishList(request):
    try:
        wish_list = request.user.wish_list
        if wish_list is None:
            return Response({'error': 'WishList not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = WishListSerializer(wish_list)
        return Response(serializer.data)

    except WishList.DoesNotExist:
        return Response({'error': 'WishList not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        # Catch other potential exceptions
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def getTargetWishList(request, list_id):
    try:
        wish_list = WishList.objects.get(id=list_id)
    except WishList.DoesNotExist:
        return Response({'error': 'WishList not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = WishListSerializer(wish_list)
    return Response(serializer.data)


@api_view(['POST'])
def addWishList(request):
    serializer = WishListSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PATCH'])
def updateWishList(request, list_id):
    try:
        wish_list = WishList.objects.get(id=list_id)
    except WishList.DoesNotExist:
        return Response({'error': 'WishList not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = WishListSerializer(
        instance=wish_list, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
def deleteWishList(request, list_id):
    try:
        wish_list = WishList.objects.get(id=list_id)
    except WishList.DoesNotExist:
        return Response({'error': 'WishList not found'}, status=status.HTTP_404_NOT_FOUND)

    wish_list.delete()
    return Response(status=204)
