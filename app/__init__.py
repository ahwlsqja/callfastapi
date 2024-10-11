import os
import requests

from dotenv import load_dotenv
from twilio.rest import Client

# Load Credentials from .env
load_dotenv()

# Init Twilio
twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_CLIENT = Client(twilio_account_sid, twilio_auth_token)

# Init Return-Zero
rtzr_client_id = os.getenv('RETURNZERO_CLIENT_ID')
rtzr_client_secret = os.getenv('RETURNZERO_CLIENT_SECRET')
resp = requests.post(
    'https://openapi.vito.ai/v1/authenticate',
    data={'client_id': rtzr_client_id, 'client_secret': rtzr_client_secret}
)

RTZR_TOKEN = resp.json()['access_token']