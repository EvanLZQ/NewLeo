from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from oauth2_provider.models import AccessToken


class AccessTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        access_token = request.COOKIES.get('access_token')

        if not access_token:
            return None

        try:
            token = AccessToken.objects.get(token=access_token)

            if token.is_expired():
                raise AuthenticationFailed('Access token has expired')

            return (token.user, token)
        except AccessToken.DoesNotExist:
            raise AuthenticationFailed('No such token')


# from rest_framework_simplejwt.authentication import JWTAuthentication


# class CookieJWTAuthentication(JWTAuthentication):
#     def authenticate(self, request):
#         raw_token = request.COOKIES.get('access_token')
#         if raw_token is None:
#             return None

#         validated_token = self.get_validated_token(raw_token)
#         print(f"validate token: {validated_token}")
#         return self.get_user(validated_token), validated_token
