import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from twilio.twiml.voice_response import VoiceResponse
import websockets

from ..service import LLAMACHAT
from .. import RTZR_TOKEN

# import base64
# import json
import time

# from elevenlabs import VoiceSettings
# import aiofiles

router = APIRouter(
    prefix='/twilio',
)

metadata = {
    'name': 'Twilio',
    'description': 'Call Service'
}

response_queues = {}

@router.post('/twiml/start', tags=['Twilio'])
async def start(request: Request) -> Response:
    twilio_response = VoiceResponse()
    body = await request.form()
    print(f'body: {body}')
    call_sid = body.get('CallSid')
  
    if call_sid:
        response_queues[call_sid] = asyncio.Queue()

        stream_url = f"wss://{request.url.hostname}/twilio/stream"
        twilio_response.start().stream(url=stream_url, track='inbound_track')
        twilio_response.say('Hello?', voice="Polly.Amy", language="en-US")

        # await continue_call(request, twilio_response)

        response_queues[call_sid] = ''

    else:
        twilio_response.say('Something went wrong! Please try again later.')
    
    return Response(content=str(twilio_response), media_type="application/xml")




@router.websocket('/stream')
async def audio_stream_handler(websocket: WebSocket) -> Response:
    print('WebSocket connection attempt')
    await websocket.accept()  # Accept the WebSocket connection from Twilio

    call_sid_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    # Try to connect to the Returnzero WebSocket
    returnzero_websocket = await open_returnzero_websocket()
    if returnzero_websocket is None:
        await websocket.close(code=1011, reason="Failed to connect to Returnzero WebSocket")
        return

    try:
        # Handle asynchronous tasks (like processing media and messages)
        tasks = [
            # asyncio.create_task(stream_audio_to_rtzr(audio_queue, returnzero_websocket)),
            # asyncio.create_task(handle_rtzr_messages(call_sid_queue, returnzero_websocket)),
            # asyncio.create_task(handle_twilio_messages(call_sid_queue, audio_queue, websocket)),
        ]
        await asyncio.gather(*tasks)

    except WebSocketDisconnect:
        print("Twilio WebSocket disconnected")

    finally:
        await returnzero_websocket.close()  # Close Returnzero WebSocket
        await websocket.close()  # Close the WebSocket

    # Return the proper response to Twilio after handling WebSocket tasks
    twilio_response = f'<Response><Say>Hello from Twilio WebSocket!</Say></Response>'
    return Response(content=twilio_response, media_type='application/xml')

        
async def open_returnzero_websocket():
    config = {
        "sample_rate": "8000",
        "encoding": "MULAW",  # Twilio가 MULAW 방식 사용
        "use_itn": "true",
        "use_disfluency_filter": "false",
        "use_profanity_filter": "false",
    }
    config_str = "&".join(f"{key}={value}" for key, value in config.items())

    # Returnzero WebSocket 엔드포인트
    STREAMING_ENDPOINT = f"wss://openapi.vito.ai/v1/transcribe:streaming?{config_str}"

    # 헤더 설정
    headers = {
        "Authorization": f"Bearer {RTZR_TOKEN}"
    }

    try:
        returnzero_websocket = await websockets.connect(STREAMING_ENDPOINT, extra_headers=headers)
        print("Connected to Returnzero WebSocket.")
        return returnzero_websocket
    
    except Exception as e:
        print(f"Failed to connect to Returnzero WebSocket: {e}")
        return None



@router.get('/test/llama', tags=['Twilio'])
def test(user_input, call_sid, is_new, prompt, instruction) -> str:
    res = LLAMACHAT.get_response(user_input, call_sid, is_new, prompt, instruction)
    return res
