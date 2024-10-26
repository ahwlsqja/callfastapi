import asyncio
import base64
import json
import logging
import os
import requests

from aiohttp import web, ClientSession, ClientWebSocketResponse, WSMsgType
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import StreamingResponse
from twilio.twiml.voice_response import VoiceResponse

from .. import RTZR_TOKEN
from ..service.tts import tts_stream_generator
from ..service.stt import open_rtzr_ws, stream_audio_to_rtzr, handle_rtzr_messages, handle_twilio_messages

router = APIRouter(
    prefix='/twilio',
)

metadata = {
    'name': 'Twilio',
    'description': 'Call Service'
}

async def continue_call(request: Request, twilio_response: VoiceResponse) -> Response:
    body = await request.form()
    call_sid = body.get('CallSid')

    if call_sid:
        redirect_url = request.url_for('twiml_continue', call_sid=call_sid)
        twilio_response.redirect(url=str(redirect_url), method='POST')
    else:
        twilio_response.say('Something went wrong. Please try again later.')

    return Response(content=str(twilio_response), media_type="text/xml")



@router.websocket("/stream")
async def audio_stream_handler(websocket: WebSocket):
    await websocket.accept()
    session: ClientSession = websocket.app.state.session  # main.py에서 생성한 세션 사용

    call_sid_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    # Returnzero WebSocket 연결
    rtzr_ws = await open_rtzr_ws(session, RTZR_TOKEN)
    logging.info("Returnzero WebSocket opened")

    try:
        tasks = [
            asyncio.create_task(stream_audio_to_rtzr(audio_queue, rtzr_ws)),
            asyncio.create_task(handle_rtzr_messages(call_sid_queue, rtzr_ws, websocket)),
            asyncio.create_task(handle_twilio_messages(call_sid_queue, audio_queue, websocket)),
        ]

        await asyncio.gather(*tasks)

    finally:
        await rtzr_ws.close()


@router.post("/twilio/twiml/continue/{call_sid}", name="twiml_continue")
async def twiml_continue(request: Request, call_sid: str) -> Response:
    logging.info('Continuing with call_sid: %s', call_sid)

    logging.info('Received request with body: %s', await request.body())

    response_queue = request.app.state.response_queues.get(call_sid)

    if not response_queue:
        logging.error(f"Response queue for call_sid {call_sid} not found.")
        return Response(content="Error: Response queue not found.", media_type="text/xml")

    twilio_response = VoiceResponse()

    try:
        next_transcript = await response_queue.get()
    except Exception as e:
        logging.error(f"Error getting transcript: {str(e)}")
        return Response(content="Error: Failed to retrieve transcript.", media_type="text/xml")

    # Ensure the response_queue is of the correct type
    if not isinstance(response_queue, asyncio.Queue):
        logging.error(f"response_queue for call_sid {call_sid} is not a Queue. Got: {type(response_queue)}")
        return Response(content="Error: Invalid response queue.", media_type="text/xml")

    # Handling the transcript response
    if next_transcript == 'END_TRANSCRIPT_MARKER':
        twilio_response.say('Thank you for calling. Goodbye!', voice="Polly.Amy", language="en-US")
    else:
        if "Assistant:" in next_transcript:
            assistant_response = next_transcript.split("Assistant:", 1)[1].strip()
        else:
            assistant_response = next_transcript.strip()

        # Create a streaming URL endpoint for this transcript
        stream_url = f"{request.url.scheme}://{request.url.netloc}/twilio/elevenlabs/stream/{call_sid}"
        request.app.state.convos[call_sid] = assistant_response
        twilio_response.play(stream_url)

        # Call continue_call, ensure it returns a proper Response
        return await continue_call(request, twilio_response)

    # Return the final response
    return Response(content=str(twilio_response), media_type="text/xml")

@router.get('/elevenlabs/stream/{call_sid}')
async def elevenlabs_stream_handler(call_sid: str, request: Request):
    """Stream TTS audio from ElevenLabs directly to Twilio."""
    transcript = request.app.state.convos.get(call_sid, '')

    # Get the ElevenLabs API key from the application context
    elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY')
    voice_id = "pMsXgVXv3BLzUgSXRplE"  # Replace with your desired voice ID

    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": transcript,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.1,
            "similarity_boost": 0.3,
            "style": 0.2,
        }
    }

    return StreamingResponse(tts_stream_generator(voice_id=voice_id), media_type="audio/mpeg")

@router.post('/twiml/start', tags=['Twilio'])
async def start(request: Request) -> Response:
    twilio_response = VoiceResponse()
    body = await request.form()
    call_sid = body.get('CallSid')

    if call_sid:
        # response_queues[call_sid]에 항상 asyncio.Queue()를 할당
        if call_sid not in request.app.state.response_queues:
            request.app.state.response_queues[call_sid] = asyncio.Queue()  # 항상 큐로 초기화

        stream_url = f"wss://{request.url.hostname}/twilio/stream"
        twilio_response.start().stream(url=stream_url, track='inbound_track')
        twilio_response.say('Hello?', voice="Polly.Amy", language="en-US")

        await continue_call(request, twilio_response)

        request.app.state.convos[call_sid] = ''

    else:
        twilio_response.say('Something went wrong! Please try again later.')

    return Response(content=str(twilio_response), media_type="text/xml")
