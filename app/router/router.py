import asyncio
import logging
import os

from aiohttp import ClientSession
from fastapi import APIRouter, WebSocket, Request, Response
from fastapi.responses import StreamingResponse
from twilio.twiml.voice_response import VoiceResponse
import psycopg2

from .. import RTZR_TOKEN, HOST, DATABASE, USER, PASSWORD
from ..service.tts import tts_stream_generator
from ..service.stt import open_rtzr_ws, stream_audio_to_rtzr, handle_rtzr_messages, handle_twilio_messages

#twilio
router = APIRouter(
    prefix='/twilio',
)

metadata = {
    'name': 'Twilio',
    'description': 'Call Service'
}

# @router.get('/test/postgres/')
def transcribe(gpt_id: str = None, voice_id: str = None):
    # PostgreSQL
    connection = psycopg2.connect(
        HOST,
        DATABASE,
        USER,
        PASSWORD
    )
    cursor = connection.cursor()

    try:
        # model_id
        if gpt_id:
            print(f'[INFO] EXECUTE transcribe() - model_id: {gpt_id}')
            cursor.execute("UPDATE your_table SET gpt_id = %s WHERE {} = %s".format())
        # voice_id
        if voice_id:
            print(f'[INFO] EXECUTE transcribe() - voice_id: {voice_id}')
            cursor.execute("UPDATE your_table SET voice_id = %s WHERE {} = %s".format())

        connection.commit()

    except Exception as e:
        print("Error updating record:", e)
        connection.rollback()  # 오류 시 롤백
    finally:
        cursor.close()
        connection.close()

@router.post('/twiml/start', tags=['Twilio'])
async def start(request: Request) -> Response:
    twilio_response = VoiceResponse()
    body = await request.form()
    call_sid = body.get('CallSid')

    if call_sid:
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
        voice_id = 'pMsXgVXv3BLzUgSXRplE'
        stream_url = f"{request.url.scheme}://{request.url.netloc}/twilio/elevenlabs/stream/{call_sid}/{voice_id}"
        request.app.state.convos[call_sid] = assistant_response
        twilio_response.play(stream_url)

        # Call continue_call, ensure it returns a proper Response
        return await continue_call(request, twilio_response)

    # Return the final response
    return Response(content=str(twilio_response), media_type="text/xml")

async def continue_call(request: Request, twilio_response: VoiceResponse) -> Response:
    body = await request.form()
    call_sid = body.get('CallSid')

    if call_sid:
        redirect_url = request.url_for('twiml_continue', call_sid=call_sid)
        twilio_response.redirect(url=str(redirect_url), method='POST')
    else:
        twilio_response.say('Something went wrong. Please try again later.')

    return Response(content=str(twilio_response), media_type="text/xml")


@router.get('/elevenlabs/stream/{call_sid}/{voice_id}')
async def elevenlabs_stream_handler(call_sid: str, voice_id: str, request: Request):
    transcript = request.app.state.convos.get(call_sid, '')

    elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY')

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

    return StreamingResponse(tts_stream_generator(voice_id=voice_id, headers=headers, payload=payload), media_type="audio/mpeg")
