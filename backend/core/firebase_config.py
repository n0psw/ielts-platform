import firebase_admin
from firebase_admin import credentials, auth
import os

cred_path = os.path.join(os.path.dirname(__file__), 'firebase_credentials.json')

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def verify_firebase_token(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token)
        print("✅ TOKEN OK:", decoded_token)
        return decoded_token
    except Exception as e:
        print("❌ TOKEN ERROR:", e)
        return None
