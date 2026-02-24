from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@csrf_exempt
def upload_image(request):
    pass


@require_GET
@ensure_csrf_cookie
def csrf(request):
    """
    Returns CSRF token in JSON and also ensures the csrftoken cookie is set.
    This allows localhost frontend to obtain the token without reading cookie.
    """
    return JsonResponse({"csrfToken": get_token(request)})
