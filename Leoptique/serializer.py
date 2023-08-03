from rest_framework_simplejwt.serializers import TokenRefreshSerializer


class CookieTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        print(self.context['request'].COOKIES.get('refresh_token'))
        refresh_token = attrs.get('refresh')
        if not refresh_token:
            refresh_token = self.context['request'].COOKIES.get(
                'refresh_token')
            if refresh_token:
                attrs['refresh'] = refresh_token
        return super().validate(attrs)
