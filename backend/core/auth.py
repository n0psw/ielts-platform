from rest_framework.authentication import BaseAuthentication
from core.firebase_config import verify_firebase_token
from core.models import User
from rest_framework.exceptions import AuthenticationFailed

class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]
        decoded_token = verify_firebase_token(token)
        if not decoded_token:
            raise AuthenticationFailed("Invalid Firebase token")

        uid = decoded_token['uid']
        try:
            user = User.objects.get(uid=uid)
            return (user, None)
        except User.DoesNotExist:
            raise AuthenticationFailed("User not found")