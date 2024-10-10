from fastapi import APIRouter

router = APIRouter(
    prefix='/twilio',
)

metadata = {
    'name': 'Twilio',
    'description': 'Call Service'
}

@router.get('/twiml/start', tags=['Twilio'])
def start():
    pass

@router.get('/twiml/stream', tags=['Twilio'])
def stream():
    pass