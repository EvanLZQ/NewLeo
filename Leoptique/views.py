from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializer import CookieTokenRefreshSerializer


class CookieTokenObtainPairView(TokenObtainPairView):
    def finalize_response(self, request, response, *args, **kwargs):
        if response.status_code == 200:
            # TODO: add secure = true when deploy
            response.set_cookie(
                'refresh_token', response.data['refresh'], httponly=True, samesite='None')
            response.set_cookie(
                'access_token', response.data['access'], httponly=True, samesite='None')
            response.data = {}
        return super().finalize_response(request, response, *args, **kwargs)


class CookieTokenRefreshView(TokenRefreshView):
    print("here")

    def create(self, request, *args, **kwargs):
        print(request.COOKIES.get('refresh_token'))
        return super().create(request, *args, **kwargs)

    serializer_class = CookieTokenRefreshSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        if response.status_code == 200:
            # TODO: add secure = true when deploy
            response.set_cookie(
                'refresh_token', response.data['refresh'], httponly=True, samesite='None')
            response.set_cookie(
                'access_token', response.data['access'], httponly=True, samesite='None')
            response.data = {}
        return super().finalize_response(request, response, *args, **kwargs)
