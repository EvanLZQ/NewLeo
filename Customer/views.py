from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, login, logout
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from General.models import Coupon, Address
from General.serializer import CustomerCouponSerializer, ImageSerializer, AddressSerializer
from rest_framework.parsers import MultiPartParser
from django.conf import settings
from Prescription.models import PrescriptionInfo
from Prescription.serializer import PrescriptionSerializer
from .serializer import *
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from Leoptique.authentication import AccessTokenAuthentication
from google.oauth2 import id_token
from django.utils import timezone
import uuid
import datetime
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import CustomerInfo, ShoppingCart, StoreCreditActivity, WishList, PasswordResetCode
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework.permissions import AllowAny
from google.auth.transport import requests as google_requests
import uuid
from django.core.cache import cache
from Order.serializer import OrderSerializer
from Order.models import OrderInfo
from Leoptique.client_ip import get_client_ip
# from django.contrib.auth.backends import ModelBackend

# Create your views here.

User = get_user_model()

# Backend used when logging a user in without authenticate() (sign-up,
# guest -> account). Several AUTHENTICATION_BACKENDS are configured, so
# login() refuses to guess and raises unless one is named.
MODEL_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _rate_limit_response():
    # A fresh Response per request: a shared module-level instance would carry
    # cookies that middleware set on it for one visitor over to the next.
    return Response(
        {'error': 'Too many attempts. Please try again later.'},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _is_rate_limited(key, max_attempts=5, window=300):
    """Return True if rate limit exceeded. window = seconds (default 5 min)."""
    count = cache.get(key, 0)
    if count >= max_attempts:
        return True
    cache.set(key, count + 1, window)
    return False


def _rate_limit_reached(key, max_attempts=5):
    return cache.get(key, 0) >= max_attempts


def _record_failure(key, window=300):
    cache.set(key, cache.get(key, 0) + 1, window)


def _normalize_email(value):
    return (value or '').strip().lower()


def _find_user_by_email(email):
    """Case-insensitive lookup; accounts created before emails were
    normalised may have mixed-case usernames."""
    return User.objects.filter(username__iexact=email).order_by('id').first()


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
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getShoppingCart(request, cart_id):
    if not request.user.shopping_cart_id or cart_id != request.user.shopping_cart_id:
        return Response({'error': 'Shopping cart not found'}, status=status.HTTP_404_NOT_FOUND)
    shopping_cart = ShoppingCart.objects.get(id=cart_id)
    serializer = ShoppingCartSerializer(shopping_cart)
    return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getUserShoppingCart(request, cart_id):
    user = request.user
    shopping_cart = user.shopping_cart

    # Guard: if the FK was set to NULL (cart deleted), lazily create a new one
    if shopping_cart is None:
        shopping_cart = ShoppingCart.objects.create()
        CustomerInfo.objects.filter(pk=user.pk).update(shopping_cart=shopping_cart)

    # cart_id (URL param) is NOT trusted for merging — it's just a client-side
    # cache-consistency hint ("is this still my cart?"), not proof of
    # ownership of whatever cart that id happens to point to. The only cart
    # ever merged in is the one tied to *this request's own session* below.

    _merge_session_guest_cart(request, shopping_cart)

    serializer = ShoppingCartSerializer(shopping_cart)
    return Response(serializer.data)


def _merge_session_guest_cart(request, shopping_cart):
    """Move the items of this session's guest cart (if any) into the
    account's cart. Called by every endpoint that hands a signed-in customer
    their cart, so items added before signing in are never left behind."""
    guest_cart_id = request.session.get("guest_cart_id")
    if not guest_cart_id:
        return
    if guest_cart_id != shopping_cart.id:
        try:
            guest_cart = ShoppingCart.objects.get(id=guest_cart_id)
            shopping_cart.merge_with(guest_cart)
        except ShoppingCart.DoesNotExist:
            pass
    del request.session["guest_cart_id"]


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def createShoppingCart(request):
    if request.user.shopping_cart_id:
        # Already has one — behave like a fetch rather than minting a second,
        # orphaned cart the user's shopping_cart FK will never point to.
        cart = request.user.shopping_cart
        _merge_session_guest_cart(request, cart)
        serializer = ShoppingCartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = ShoppingCartSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        cart = serializer.save()
        CustomerInfo.objects.filter(pk=request.user.pk).update(shopping_cart=cart)
        _merge_session_guest_cart(request, cart)
        return Response(ShoppingCartSerializer(cart).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def updateShoppingCart(request, cart_id):
    if not request.user.shopping_cart_id or cart_id != request.user.shopping_cart_id:
        return Response({'error': 'Shopping cart not found'}, status=status.HTTP_404_NOT_FOUND)

    shopping_cart = ShoppingCart.objects.get(id=cart_id)
    serializer = ShoppingCartSerializer(
        instance=shopping_cart, data=request.data, partial=True, context={'request': request})

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def login_view(request):
    ip = get_client_ip(request)
    rl_key = f'rl:login:{ip}'
    # Only failed attempts count, so a customer who signs in and out a few
    # times (or several people behind one IP) is not locked out.
    if _rate_limit_reached(rl_key, max_attempts=10):
        return _rate_limit_response()

    username = _normalize_email(request.data.get('username'))
    password = request.data.get('password') or ''
    existing = _find_user_by_email(username) if username else None
    user = authenticate(
        request,
        username=existing.username if existing else username,
        password=password,
    )
    if user is not None:
        login(request, user)
        return Response({"message": "Login successful!"})
    _record_failure(rl_key)
    return Response({"error": "Invalid credentials"}, status=400)


@api_view(['POST'])
def logout_view(request):
    logout(request)
    response = Response({"message": "Logged out successfully!"})
    # Expire the OAuth cookies so AccessTokenAuthentication can no longer
    # resolve the old user between logout and the next login.
    response.delete_cookie("access_token",  path="/", domain=settings.COOKIE_DOMAIN, samesite="None")
    response.delete_cookie("refresh_token", path="/", domain=settings.COOKIE_DOMAIN, samesite="None")
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def google_login(request):
    credential = request.data.get("credential")
    if not credential:
        return Response({"error": "Missing credential"}, status=400)

    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        return Response({"error": "Server misconfigured: missing GOOGLE_OAUTH_CLIENT_ID"}, status=500)

    # verify against server-side Google client id (NOT request.data["clientId"])
    try:
        id_info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
        if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
            return Response({"error": "Wrong issuer"}, status=400)
    except Exception:
        return Response({"error": "Invalid token"}, status=400)

    email = id_info.get("email")
    if not email:
        return Response({"error": "Missing email"}, status=400)

    if id_info.get("email_verified") is not True:
        return Response({"error": "Email not verified"}, status=400)

    family_name = id_info.get("family_name", "")
    given_name = id_info.get("given_name", "")
    picture = id_info.get("picture", "")

    user, created = CustomerInfo.objects.get_or_create(
        username=email,
        defaults={"first_name": given_name,
                  "last_name": family_name, "icon_url": picture},
    )
    if not created:
        user.first_name = given_name
        user.last_name = family_name
        user.icon_url = picture
        user.save()

    # Send welcome email for first-time Google users
    if created:
        try:
            from Customer.email_service import send_welcome_email
            send_welcome_email(user)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Failed to send welcome email to %s', email
            )

    # get DOT Application by stable name; create if missing
    application, _ = Application.objects.get_or_create(
        name="eyelovewear-web",
        defaults={
            "client_type": Application.CLIENT_CONFIDENTIAL,
            "authorization_grant_type": Application.GRANT_PASSWORD,  # or whatever you use
        },
    )

    access_token_value = uuid.uuid4().hex  # better than str(uuid.uuid4())
    token = AccessToken.objects.create(
        user=user,
        token=access_token_value,
        application=application,
        expires=timezone.now() + datetime.timedelta(days=1),
        scope="read write",
    )

    refresh_token = RefreshToken.objects.create(
        user=user,
        token=uuid.uuid4().hex,
        access_token=token,
        application=application,
    )

    user.backend = "django.contrib.auth.backends.ModelBackend"
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

    # cookie settings: samesite must be "None" string when secure cross-site
    response.set_cookie(
        "access_token",
        token.token,
        max_age=3600 * 24,
        samesite="None",
        domain=settings.COOKIE_DOMAIN,
        path="/",
        httponly=True,
        secure=True,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token.token,
        max_age=3600 * 24 * 30,
        samesite="None",
        domain=settings.COOKIE_DOMAIN,
        path="/",
        httponly=True,
        secure=True,
    )
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
    from django.core.validators import validate_email

    data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
    email = _normalize_email(data.get('username'))
    password = data.get('password') or ''
    try:
        validate_email(email)
    except ValidationError:
        return Response({'username': ['Please enter a valid email address.']}, status=400)
    if _find_user_by_email(email):
        return Response({'username': ['An account with this email already exists.']}, status=400)
    try:
        validate_password(password, user=CustomerInfo(username=email, email=email))
    except ValidationError as e:
        return Response({'password': e.messages}, status=400)
    data['username'] = email

    serializer = CustomerCreateSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        login(request, serializer.instance, backend=MODEL_BACKEND)
        try:
            from Customer.email_service import send_welcome_email
            send_welcome_email(serializer.instance)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Failed to send welcome email to %s', getattr(serializer.instance, 'email', 'unknown')
            )
        return Response("User created successfully", status=201)
    return Response(serializer.errors, status=400)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getCustomerOrders(request):
    user = request.user
    # Only orders the customer actually paid for. An UNPAID row is a checkout
    # attempt (created when the payment step opens, cancelled when they step
    # back); listing those made every abandoned attempt look like a
    # "Canceled" order the customer never placed. Staff still see them all.
    orders = OrderInfo.objects.filter(customer=user).exclude(payment_status='UNPAID')
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
    from django.db.models import Q
    from django.utils import timezone

    user = request.user
    # valid_customer empty means "valid for every customer" (same rule
    # Order/service/order_service.py's is_coupon_applicable uses) — a
    # plain `valid_customer=user` filter would only ever show coupons
    # this customer was individually added to and silently hide every
    # general/sitewide promo code, which is most of them.
    coupon = Coupon.objects.filter(online=True).filter(
        Q(valid_customer=user) | Q(valid_customer__isnull=True)
    ).filter(
        Q(expire_date__isnull=True) | Q(expire_date__gte=timezone.now().date())
    ).distinct()
    serializer = CustomerCouponSerializer(coupon, many=True)
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
        prescription = PrescriptionInfo.objects.get(id=prescription_id, customer=request.user)
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
        address = Address.objects.get(id=address_id, customer=request.user)
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
        address = Address.objects.get(id=address_id, customer=request.user)
    except Address.DoesNotExist:
        return Response({'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)

    address.delete()
    return Response(status=204)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def getUserWishList(request):
    user = request.user
    wish_list = user.wish_list

    # Guard: if the FK was set to NULL (wish list deleted), lazily create a new one
    if wish_list is None:
        wish_list = WishList.objects.create()
        CustomerInfo.objects.filter(pk=user.pk).update(wish_list=wish_list)

    serializer = WishListSerializer(wish_list)
    return Response(serializer.data)


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


User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset_code(request):
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response(
            {'error': 'Email is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    generic_msg = 'If an account with that email exists, a verification code has been sent.'

    if not PasswordResetCode.can_request(email):
        return Response({'message': generic_msg}, status=status.HTTP_200_OK)

    user = _find_user_by_email(email)
    if user is None:
        return Response({'message': generic_msg}, status=status.HTTP_200_OK)

    code = PasswordResetCode.generate_code()
    reset_obj = PasswordResetCode(email=email)
    reset_obj.set_code(code)
    reset_obj.save()

    try:
        from Customer.email_service import send_password_reset_code
        send_password_reset_code(email, code, user.first_name)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send password reset code to %s', email
        )

    return Response({'message': generic_msg}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_password_reset_code(request):
    email = (request.data.get('email') or '').strip().lower()
    code = (request.data.get('code') or '').strip()

    if email and _is_rate_limited(f'rl:verify:{email}'):
        return _rate_limit_response()

    if not email or not code:
        return Response(
            {'error': 'Email and code are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        reset_code = PasswordResetCode.objects.filter(
            email=email, used=False
        ).latest('created_at')
    except PasswordResetCode.DoesNotExist:
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not reset_code.is_valid:
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_code.attempts += 1
    reset_code.save(update_fields=['attempts'])

    if not reset_code.check_code(code):
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({'message': 'Code verified.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    email = (request.data.get('email') or '').strip().lower()
    code = (request.data.get('code') or '').strip()
    new_password = request.data.get('new_password', '')
    confirm_password = request.data.get('confirm_password', '')

    if email and _is_rate_limited(f'rl:reset:{email}'):
        return _rate_limit_response()

    if not all([email, code, new_password, confirm_password]):
        return Response(
            {'error': 'All fields are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if new_password != confirm_password:
        return Response(
            {'error': 'Passwords do not match.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        reset_code = PasswordResetCode.objects.filter(
            email=email, used=False
        ).latest('created_at')
    except PasswordResetCode.DoesNotExist:
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not reset_code.is_valid:
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_code.attempts += 1
    reset_code.save(update_fields=['attempts'])

    if not reset_code.check_code(code):
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = _find_user_by_email(email)
    if user is None:
        return Response(
            {'error': 'Invalid or expired code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(new_password, user=user)
    except ValidationError as e:
        return Response(
            {'error': e.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save()

    reset_code.used = True
    reset_code.save(update_fields=['used'])
    PasswordResetCode.objects.filter(email=email, used=False).update(used=True)

    return Response(
        {'message': 'Password reset successfully.'},
        status=status.HTTP_200_OK,
    )


# ── Guest → Account creation (post-purchase) ─────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def createFromGuest(request):
    """
    Create an account from a guest checkout and link the guest order.

    POST body:
        email        – str (must match the guest order)
        password     – str
        order_number – str
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    email        = _normalize_email(request.data.get('email'))
    password     = request.data.get('password', '')
    order_number = request.data.get('order_number', '')

    if not email or not password:
        return Response({'error': 'Email and password are required'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Check if account already exists
    if _find_user_by_email(email):
        return Response({'error': 'An account with this email already exists'},
                        status=status.HTTP_409_CONFLICT)

    # Validate password strength
    try:
        validate_password(password)
    except ValidationError as e:
        return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)

    # Create the user
    user = CustomerInfo.objects.create_user(username=email, email=email, password=password)

    # Link guest order(s) to the new account
    if order_number:
        from Order.models import OrderInfo
        from General.models import Address
        guest_orders = OrderInfo.objects.filter(
            order_number=order_number, email__iexact=email, customer=None)
        for order in guest_orders:
            order.customer = user
            order.save(update_fields=['customer'])
            # Link the order's address to the customer
            if order.address and order.address.customer is None:
                Address.objects.filter(pk=order.address_id).update(customer=user)

    # Auto-login
    login(request, user, backend=MODEL_BACKEND)

    # Send welcome email
    try:
        from Customer.email_service import send_welcome_email
        send_welcome_email(user)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send welcome email to %s', email)

    return Response({'success': True, 'message': 'Account created successfully'},
                    status=status.HTTP_201_CREATED)
