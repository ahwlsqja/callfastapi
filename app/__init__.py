import os
import requests

from dotenv import load_dotenv
from twilio.rest import Client

# Load Credentials from .env
load_dotenv()

twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_CLIENT = Client(twilio_account_sid, twilio_auth_token)

# Init Return-Zero
rtzr_client_url = os.getenv('RETURNZERO_CLIENT_URL')
rtzr_client_id = os.getenv('RETURNZERO_CLIENT_ID')
rtzr_client_secret = os.getenv('RETURNZERO_CLIENT_SECRET')
resp = requests.post(
    rtzr_client_url,
    data={'client_id': rtzr_client_id, 'client_secret': rtzr_client_secret}
)
RTZR_TOKEN = resp.json()['access_token']

# PostgreSQL
HOST = os.getenv('HOST')
DATABASE = os.getenv('DATABASE')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')

ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')