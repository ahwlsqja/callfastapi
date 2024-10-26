import asyncio
import logging
import os
import requests
from aiohttp import web, ClientSession, ClientWebSocketResponse, WSMsgType
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from twilio.twiml.voice_response import VoiceResponse
import json
from fastapi.responses import StreamingResponse

# from ..service import LLAMACHAT
from .. import RTZR_TOKEN

router = APIRouter(
    prefix='/twilio',
)

metadata = {
    'name': 'Twilio',
    'description': 'Call Service'
}

SYSTEM_MESSAGE_CONTENT ="""
You are a bank representative. A customer has called with inquiries related to banking services. 
Guide the conversation by asking questions related to common banking services, such as account balance inquiries,
recent transaction history, loan eligibility, and credit card information. Respond briefly to the customer's answers 
and maintain a natural flow in the conversation. While waiting for the API response, keep prompting the customer with 
relevant questions and inform them appropriately when information is being checked or processed. Be courteous and 
provide a trustworthy experience. Always respond in Korean, using simple and clear language. Always answer in Korean
"""

# Number of milliseconds of silence that mark the end of a user interaction.
ENDPOINTING_DELAY = 4000

# A sentinel to mark the end of a transcript stream
END_TRANSCRIPT_MARKER = 'END_TRANSCRIPT_MARKER'

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

async def continue_call(request: Request, twilio_response: VoiceResponse) -> Response:
    """Continue a call by adding a Redirect instruction to a TwiML Response."""
    body = await request.form()
    call_sid = body.get('CallSid')

    if call_sid:
        redirect_url = request.url_for('twiml_continue', call_sid=call_sid)
        twilio_response.redirect(url=str(redirect_url), method='POST')
    else:
        twilio_response.say('Something went wrong. Please try again later.')

    # 항상 Response 객체를 반환하도록 보장
    return Response(content=str(twilio_response), media_type="text/xml")


@router.post("/twilio/twiml/continue/{call_sid}", name="twiml_continue")
async def twiml_continue(request: Request, call_sid: str) -> Response:
    logging.info('Continuing with call_sid: %s', call_sid)

    # 로그 추가
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
    if next_transcript == END_TRANSCRIPT_MARKER:
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

    async def tts_stream_generator():
        async with ClientSession() as session:
            try:
                async with session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        logging.error(f"Failed to stream TTS from ElevenLabs. Status: {response.status}")
                        raise Exception(f"Failed to stream TTS from ElevenLabs. Status: {response.status}")

                    # Stream the content as received from ElevenLabs to Twilio
                    async for chunk in response.content.iter_chunked(1024):
                        if not chunk:
                            break
                        yield chunk

            except Exception as e:
                logging.error(f"Error while streaming TTS from ElevenLabs: {str(e)}")
                raise Exception(f"Error while streaming TTS from ElevenLabs: {str(e)}")

    return StreamingResponse(tts_stream_generator(), media_type="audio/mpeg")

@router.websocket("/stream")
async def audio_stream_handler(websocket: WebSocket):
    await websocket.accept()
    session: ClientSession = websocket.app.state.session  # main.py에서 생성한 세션 사용

    call_sid_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    # Returnzero WebSocket 연결
    rtzr_ws = await open_rtzr_ws(session, init_rtzr())
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

async def stream_audio_to_rtzr(audio_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse):
    """Handle streaming audio to Returnzero with keep-alive pings."""

    logging.info("Starting to stream audio to Returnzero WebSocket")
    while True:
        chunk = await audio_queue.get()
        logging.info(f"Received chunk of type {type(chunk)}")

        if chunk == "EOS":
            logging.info("End of Stream detected, sending EOS to Returnzero WebSocket")
            await rtzr_ws.send_str("EOS")
            break

        if isinstance(chunk, bytes):
            try:
                logging.info("Sending audio chunk to WebSocket")
                await rtzr_ws.send_bytes(chunk)
            except Exception as e:
                logging.error(f"Error sending audio chunk to Returnzero WebSocket: {str(e)}")
                break
        else:
            logging.warning('Unsupported message type from Twilio stream: %s', type(chunk))
            continue

    logging.info("Finished streaming audio, closing Returnzero WebSocket")
    await rtzr_ws.close()

async def handle_rtzr_messages(call_sid_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse, request: Request):
    """Handle responses from Returnzero."""
    call_sid = await call_sid_queue.get()
    logging.info('Returnzero receiver using call_sid: %s', call_sid)
    
    response_queue = request.app.state.response_queues.get(call_sid)
    if not isinstance(response_queue, asyncio.Queue):
        logging.error(f"response_queue for call_sid {call_sid} is not a Queue. Got: {type(response_queue)}")
        return

    while True:
        try:
            message = await rtzr_ws.receive()  # Receive a message from the WebSocket

            if message.type == WSMsgType.TEXT:
                msg = json.loads(message.data)
                logging.debug(f"Received text message from Returnzero WebSocket: {msg}")
                if 'final' in msg and msg['final'] == True:
                    transcript = msg['alternatives'][0]['text']
                    print(transcript)
                    if transcript:
                        logging.info(f"Final transcript received: {transcript}")
                        response = await get_chatgpt_response(call_sid, transcript, request)
                        print(f'response: {response}')
                        response_queue.put_nowait(response)
                else:
                    logging.warning(f"Warning: {msg}")

            elif message.type == WSMsgType.CLOSE:
                logging.info("Returnzero WebSocket closed.")
                response_queue.put_nowait(END_TRANSCRIPT_MARKER)
                break

        except Exception as e:
            logging.error(f"Error while receiving message from Returnzero WebSocket: {str(e)}")
            break

async def get_chatgpt_response(call_sid: str, prompt: str, request: Request) -> str:
    response = await call_chatgpt(prompt, request)
    request.app.state.convos[call_sid] += f'\n\nYou: {prompt}\n\nAssistant: {response}'

    return response

conversation = [{'role':'system', 'content': SYSTEM_MESSAGE_CONTENT}]

async def call_chatgpt(message: str, request: Request) -> str:
    session = request.app.state.session
    url = 'https://api.openai.com/v1/chat/completions'
    key = os.getenv('OPENAI_API_KEY')
    headers = {'Authorization': f"Bearer {key}"}

    conversation.append({'role': 'user', 'content': message})

    payload = {'model': 'gpt-4-0125-preview', 'messages': conversation}

    logging.info('Sending to ChatGPT -> User: %s', message)

    async with session.post(url, headers=headers, json=payload) as resp:
        if resp.status != 200:
            return ''
        resp_payload = await resp.json()
        response = resp_payload['choices'][0]['message']['content'].strip()

    conversation.append({'role': 'assistant', 'content': response})

    logging.info('ChatGPT: %s', response)

    return response

async def handle_twilio_messages(
    call_sid_queue: asyncio.Queue,
    audio_queue: asyncio.Queue,
    twilio_ws: WebSocket
):
    while True:
        try:
            message = await twilio_ws.receive_text()
            data = json.loads(message)
            
            match data['event']:
                case 'start':
                    assert data['start']['mediaFormat']['encoding'] == 'audio/x-mulaw'
                    assert data['start']['mediaFormat']['sampleRate'] == 8000
                    call_sid = data['start']['callSid']
                    call_sid_queue.put_nowait(call_sid)
                case 'media':
                    chunk = base64.b64decode(data['media']['payload'])
                    audio_queue.put_nowait(chunk)
                case 'stop':
                    break
        except WebSocketDisconnect:
            logging.info("Twilio WebSocket disconnected")
            break
        except Exception as e:
            logging.error(f"Error in Twilio message handling: {str(e)}")
            break

async def open_rtzr_ws(session: ClientSession, token: str) -> ClientWebSocketResponse:
    config = {
        "sample_rate": "8000",
        "encoding": "MULAW",
        "use_itn": "true",
        "use_disfluency_filter": "false",
        "use_profanity_filter": "false",
    }
    config_str = "&".join(f"{key}={value}" for key, value in config.items())

    STREAMING_ENDPOINT = f"wss://openapi.vito.ai/v1/transcribe:streaming?{config_str}"

    headers = {"Authorization": f"Bearer {token}"}

    rtzr_ws = await session.ws_connect(STREAMING_ENDPOINT, headers=headers)
    return rtzr_ws

def init_rtzr():
    client_id = os.getenv('RETURNZERO_CLIENT_ID')
    client_secret = os.getenv('RETURNZERO_CLIENT_SECRET')

    auth_url = 'https://openapi.vito.ai/v1/authenticate'
    auth_data = {'client_id': client_id, 'client_secret': client_secret}

    resp = requests.post(auth_url, data=auth_data)
    resp.raise_for_status()
    jwt_token = resp.json()['access_token']

    return jwt_token