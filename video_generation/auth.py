from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authtoken.models import Token
from drf_spectacular.extensions import OpenApiAuthenticationExtension

class APIKeyAuthentication(BaseAuthentication):
    keyword = 'ApiKey'

    def authenticate(self, request):
        api_key = request.META.get('HTTP_X_API_KEY')
        if not api_key:
            auth = request.headers.get('Authorization')
            if auth and auth.startswith(f'{self.keyword} '):
                api_key = auth.split(' ', 1)[1].strip()
        if not api_key:
            return None
        try:
            token = Token.objects.get(key=api_key)
        except Token.DoesNotExist:
            raise AuthenticationFailed('Invalid API key')
        return (token.user, token)

class APIKeyAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = 'video_generation.auth.APIKeyAuthentication'
    name = 'ApiKey'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'name': 'X-Api-Key',
            'in': 'header',
            'description': 'Provide your API key in X-Api-Key header',
        }
