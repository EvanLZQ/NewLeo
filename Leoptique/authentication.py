from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from oauth2_provider.models import AccessToken


class AccessTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token_value = request.COOKIES.get("access_token")

        # Optional: allow Bearer token too
        if not token_value:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token_value = auth.split(" ", 1)[1].strip()

        if not token_value:
            return None

        try:
            token = AccessToken.objects.select_related(
                "user").get(token=token_value)

            if token.is_expired():
                raise AuthenticationFailed("Access token has expired")

            return (token.user, token)
        except AccessToken.DoesNotExist:
            raise AuthenticationFailed("Invalid access token")
