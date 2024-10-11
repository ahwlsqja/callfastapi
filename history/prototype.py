import asyncio
import base64
import json
import logging
import os
import time
import requests

from elevenlabs import VoiceSettings
import aiofiles
from aiohttp import web, ClientSession, ClientWebSocketResponse, WSMsgType
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

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

routes = web.RouteTableDef()

def add_to_transcript(message):
    with open('conversation_log.txt', 'a') as file:
        file.write(message + '\n')


async def continue_call(request: web.Request, twilio_response: VoiceResponse):
    """Continue a call.

    This function adds a Redirect instruction to a TwiML Response.
    """
    body = await request.post()
    call_sid = body.get('CallSid')
    if call_sid:
        redirect_url = request.app.router['twiml_continue'].url_for(call_sid=call_sid)
        twilio_response.redirect(url=str(redirect_url), method='POST')
    else:
        twilio_response.say('Something went wrong. Please try again later.')


async def open_rtzr_ws(request: web.Request) -> ClientWebSocketResponse:
    jwt_token = request.app['rtzr_token']

    config = {
        "sample_rate": "8000",
        "encoding": "MULAW", # twilio가 mulaw 방식 사용
        "use_itn": "true",
        "use_disfluency_filter": "false",
        "use_profanity_filter": "false",
    }
    config_str = "&".join(f"{key}={value}" for key, value in config.items())

    STREAMING_ENDPOINT = f"wss://openapi.vito.ai/v1/transcribe:streaming?{config_str}"

    app_client = request.app['app_client']
    headers = {"Authorization": f"Bearer {jwt_token}"}

    rtzr_ws = await app_client.ws_connect(STREAMING_ENDPOINT, headers=headers)
    
    return rtzr_ws


# Initialize conversation list outside of your function
conversation = [{'role':'system', 'content': SYSTEM_MESSAGE_CONTENT}]

async def call_chatgpt(message: str, request: web.Request) -> str:
    app_client = request.app['app_client']
    url = 'https://api.openai.com/v1/chat/completions'
    key = os.getenv('OPENAI_API_KEY')
    headers = {
        'Authorization': f"Bearer {key}",
    }

    # Add user message to conversation
    conversation.append({'role': 'user', 'content': message})

    payload = {
        'model': 'gpt-4-0125-preview',
        'messages': conversation,
    }

    # log message being sent to ChatGPT to console
    logging.info('Sending to ChatGPT -> User: %s', message)
    add_to_transcript(f'You: {message}')

    async with app_client.post(url, headers=headers, json=payload) as resp:
        if resp.status != 200:
            return ''
        resp_payload = await resp.json()
        response = resp_payload['choices'][0]['message']['content'].strip()

    # Add bot response to conversation
    conversation.append({'role': 'assistant', 'content': response})

    # log bot response from ChatGPT to console
    logging.info('ChatGPT: %s', response)
    add_to_transcript(f'Prospect: {response}')

    return response


async def get_chatgpt_response(call_sid: str, prompt: str, request: web.Request) -> str:
    """Get a response from ChatGPT using Deepgram transcript as prompt.

    Parameters
    ----------
    prompt : str
        Prompt to send to ChatGPT. This is the transcript of a caller's interaction.
    request : aiohttp.web.Request
        Has an HTTP client used to make a request.

    Returns
    -------
    Text of ChatGPT response or a warning message if banned words are found.
    """
    BANNED_COMMANDS = [
        "chown", "chgrp", "useradd", "userdel", "id", "who", "whoami", "logname",
        "w", "last", "groups", "newgrp", "stty", "setserial", "getty", "mesg",
        "wall", "dmesg", "uname", "arch", "lastcomm", "lsof", "strace", "free",
        "procinfo", "lsdev", "du", "df", "stat", "vmstat", "netstat", "uptime",
        "hostname", "hostid", "logger", "logrotate", "ps", "pstree", "top",
        "nice", "nohup", "pidof", "fuser", "crond", "init", "telinit", "runlevel",
        "halt", "shutdown", "reboot", "ifconfig", "route", "chkconfig", "tcpdump",
        "mount", "umount", "sync", "losetup", "mkswap", "swapon", "swapoff",
        "mke2fs", "tune2fs", "dumpe2fs", "hdparm", "fdisk", "fsck", "e2fsck",
        "debugfs", "badblocks", "mkbootdisk", "chroot", "lockfile", "mknod",
        "tmpwatch", "MAKEDEV", "dump", "restore", "fdformat", "ulimit", "umask",
        "rdev", "lsmod", "insmod", "modprobe", "depmod", "env", "ldd", "strip",
        "nm", "rdist", "공격"
    ]

    # Check if the prompt contains any banned words
    for command in BANNED_COMMANDS:
        if command in prompt.lower():
            warning_message = "Warning: Your input contains restricted terms. Please refrain from using such commands."
            request.app['convos'][call_sid] += f'\n\nYou: {prompt}\n\nAssistant: {warning_message}'
            return warning_message

    # Proceed with getting the response from ChatGPT
    response = await call_chatgpt(prompt, request)
    request.app['convos'][call_sid] += f'\n\nYou: {prompt}\n\nAssistant: {response}'

    return response



async def stream_audio_to_rtzr(audio_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse):
    """Handle streaming audio to Returnzero.

    Read Twilio audio from audio queue and send it to Returnzero.
    """
    logging.info("Starting to stream audio to Returnzero WebSocket")

    # Sending audio chunks
    while True:
        chunk = await audio_queue.get()

        if chunk == "EOS":
            logging.info("End of Stream detected, sending EOS to Returnzero WebSocket")
            await rtzr_ws.send_str("EOS")
            break

        if isinstance(chunk, bytes):
            # logging.debug("Sending audio chunk to Returnzero WebSocket")
            try:
                await rtzr_ws.send_bytes(chunk)
            except Exception as e:
                logging.error(f"Error sending audio chunk to Returnzero WebSocket: {str(e)}")
                break
        else:
            logging.warning('Unsupported message type from Twilio stream: %s', type(chunk))
            continue

    logging.info("Finished streaming audio, closing Returnzero WebSocket")
    await rtzr_ws.close()


async def handle_rtzr_messages(call_sid_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse, request: web.Request):
    """Handle responses from Returnzero."""
    call_sid = await call_sid_queue.get()
    logging.info('Returnzero receiver using call_sid: %s', call_sid)
    response_queue = request.app['response_queues'][call_sid]

    while True:
        try:
            message = await rtzr_ws.receive()  # Receive a message from the WebSocket

            if message.type == WSMsgType.TEXT:
                msg = json.loads(message.data)
                logging.debug(f"Received text message from Returnzero WebSocket: {msg}")
                if 'final' in msg and msg['final']:
                    transcript = msg['alternatives'][0]['text']
                    if transcript:
                        logging.info(f"Final transcript received: {transcript}")
                        response = await get_chatgpt_response(call_sid, transcript, request)
                        response_queue.put_nowait(response)

            elif message.type == WSMsgType.CLOSE:
                logging.info("Returnzero WebSocket closed.")
                response_queue.put_nowait(END_TRANSCRIPT_MARKER)
                break

            else:
                # logging.warning(f"Received unsupported message type from Returnzero WebSocket: {message.type}")
                pass

        except Exception as e:
            logging.error(f"Error while receiving message from Returnzero WebSocket: {str(e)}")
            break


async def handle_twilio_messages(
    call_sid_queue: asyncio.Queue,
    audio_queue: asyncio.Queue,
    twilio_ws: web.WebSocketResponse,
):
    """Handle messages from Twilio."""
    async for message in twilio_ws:
        match message.type:
            case WSMsgType.TEXT:
                data = message.json()
                match data['event']:
                    case 'start':
                       # Twilio should be sending us mulaw-encoded audio at 8000Hz.
                        # At least, this is what we've already told Deepgram to
                        # expect when opening our websocket stream. If not
                        # correct, we should just abort here.
                        assert data['start']['mediaFormat']['encoding'] == 'audio/x-mulaw'
                        assert data['start']['mediaFormat']['sampleRate'] == 8000
                        # Here we tell deepgram_receiver the callSid
                        call_sid = data['start']['callSid']
                        call_sid_queue.put_nowait(call_sid)
                    case 'connected':
                        pass
                    case 'media':
                        chunk = base64.b64decode(data['media']['payload'])
                        audio_queue.put_nowait(chunk)
                    case 'stop':
                        break
            case WSMsgType.CLOSE:
                break
            case _:
                logging.warning('Got unsupported message type from Twilio stream!')
    close_rtzr_stream(audio_queue)


async def close_rtzr_stream(audio_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse):
    """Send an End of Stream message to Returnzero WebSocket and close the connection."""
    try:
        # Logging the close operation
        logging.info("Sending End Of Stream (EOS) to Returnzero WebSocket")
        
        # Sending EOS to Returnzero
        await rtzr_ws.send_str("EOS")
        
        # Closing the WebSocket connection properly
        await rtzr_ws.close()
        logging.info("Returnzero WebSocket closed successfully.")
        
    except Exception as e:
        logging.error(f"Error while closing Returnzero WebSocket: {str(e)}")

    # Signal the audio queue to stop consuming chunks
    stop_message = json.dumps({'type': 'CloseStream'})
    audio_queue.put_nowait(stop_message)


async def convert_text_to_speech(elevenlabs_client, text):
    """Converts text to speech using ElevenLabs API and saves it to a file."""
    try:
        voice_id = "pMsXgVXv3BLzUgSXRplE"  # Replace with the actual voice ID you want to use
        output_format = "mp3_22050_32"
        
        # Set up file path to save the generated audio
        audio_file_path = f"/tmp/{voice_id}_{int(time.time())}.mp3"

        # Convert text to speech as a stream (synchronous generator)
        stream = elevenlabs_client.text_to_speech.convert_as_stream(
            voice_id=voice_id,
            text=text,
            output_format=output_format,
            voice_settings=VoiceSettings(stability=0.1, similarity_boost=0.3, style=0.2),
        )

        # Open the file asynchronously for writing
        async with aiofiles.open(audio_file_path, 'wb') as audio_file:
            for chunk in stream:  # Synchronous iteration over the generator
                await audio_file.write(chunk)

        logging.info(f"TTS audio generated and saved to {audio_file_path}")
        return audio_file_path

    except Exception as e:
        logging.error(f"Error generating TTS from ElevenLabs: {str(e)}")
        return None



@routes.get('/elevenlabs/stream/{call_sid}')
async def elevenlabs_stream_handler(request: web.Request):
    """Stream TTS audio from ElevenLabs directly to Twilio."""
    call_sid = request.match_info['call_sid']
    transcript = request.app['convos'].get(call_sid, '')

    # Get the ElevenLabs API key from the application context
    elevenlabs_api_key = request.app['elevenlabs_api_key']
    voice_id = "pMsXgVXv3BLzUgSXRplE"  # Replace with your desired voice ID

    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": transcript,
        # "model_id": "eleven_turbo_v2_5",
        # "language_code": "ko",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.1,
            "similarity_boost": 0.3,
            "style": 0.2,
        }
    }

    # Prepare the streaming response
    stream_response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "audio/mpeg",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        }
    )

    # Start streaming TTS audio to Twilio
    try:
        # Start the ElevenLabs streaming session
        await stream_response.prepare(request)

        async with ClientSession() as session:
            async with session.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    logging.error(f"Failed to stream TTS from ElevenLabs. Status: {response.status}")
                    return web.Response(status=500, text="Failed to stream TTS from ElevenLabs")

                # Stream the content as received from ElevenLabs to Twilio
                async for chunk in response.content.iter_chunked(1024):
                    if not chunk:
                        break
                    await stream_response.write(chunk)

    except Exception as e:
        logging.error(f"Error while streaming TTS from ElevenLabs: {str(e)}")
        return web.Response(status=500, text="Error while streaming TTS from ElevenLabs")

    finally:
        await stream_response.write_eof()

    return stream_response



@routes.post('/twilio/twiml/continue/{call_sid}', name='twiml_continue')
async def twiml_continue(request: web.Request) -> web.Response:
    """Chat continuation handler.

    Handle bot responses to the caller by converting text to speech using ElevenLabs streaming.
    """
    call_sid = request.match_info['call_sid']
    logging.info('Continuing with call_sid: %s', call_sid)
    response_queue = request.app['response_queues'].get(call_sid)

    twilio_response = VoiceResponse()
    next_transcript = await response_queue.get()

    if next_transcript == END_TRANSCRIPT_MARKER:
        twilio_response.say('Thank you for calling. Goodbye!', voice="Polly.Amy", language="en-US")
    else:
        # Extract only the assistant's response to be used in TTS
        if "Assistant:" in next_transcript:
            assistant_response = next_transcript.split("Assistant:", 1)[1].strip()
        else:
            assistant_response = next_transcript.strip()

        # Create a streaming URL endpoint for this transcript
        stream_url = f"{request.scheme}://{request.host}/elevenlabs/stream/{call_sid}"

        # Update the conversation to include only the response
        request.app['convos'][call_sid] = assistant_response

        # Play the generated audio stream using Twilio
        twilio_response.play(stream_url)

        await continue_call(request, twilio_response)

    response = web.Response(text=str(twilio_response))
    response.content_type = 'text/html'

    return response


@routes.post('/twilio/twiml/start')
async def start(request: web.Request) -> web.Response:
    twilio_response = VoiceResponse()
    body = await request.post()
    # print('incoming call body:', body)
    call_sid = body.get('CallSid')
    if call_sid:
        response_queues = request.app['response_queues']
        response_queues[call_sid] = asyncio.Queue()
        host = request.host
        stream_url = f"wss://{host}/twilio/stream"
        # logging.info('Got websocket URL: %s', stream_url)

        twilio_response.start().stream(url=stream_url, track='inbound_track')
        twilio_response.say('Hello?', voice="Polly.Amy", language="en-US")
        # audio_url = "https://drive.google.com/file/d/11WSde3rG61yvZAgCqbYdaeRzG18ZTh3e/view?usp=sharing"
        # twilio_response.play(audio_url)
        await continue_call(request, twilio_response)

        request.app['convos'][call_sid] = ''
    else:
        logging.error('Expected payload from Twilio with a CallSid value!')
        twilio_response.say('Something went wrong! Please try again later.')

    response = web.Response(text=str(twilio_response))
    response.content_type = 'text/html'

    return response



@routes.get('/twilio/stream')
async def audio_stream_handler(request: web.Request) -> web.WebSocketResponse:
    """Open a websocket connection from Twilio."""
    twilio_ws = web.WebSocketResponse()
    await twilio_ws.prepare(request)

    call_sid_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    # Connect to the Returnzero WebSocket endpoint
    rtzr_ws = await open_rtzr_ws(request)
    if rtzr_ws is None:
        logging.error('Failed to open Returnzero WebSocket connection.')
        return web.Response(status=500, text='Failed to establish Returnzero connection')

    try:
        logging.info('Opened connection to Returnzero for streaming.')
        tasks = [
            asyncio.create_task(
                stream_audio_to_rtzr(audio_queue, rtzr_ws)
            ),
            asyncio.create_task(
                handle_rtzr_messages(call_sid_queue, rtzr_ws, request)
            ),
            asyncio.create_task(
                handle_twilio_messages(call_sid_queue, audio_queue, twilio_ws)
            ),
        ]
        await asyncio.gather(*tasks)
    finally:
        await rtzr_ws.close()

    return twilio_ws


async def app_factory() -> web.Application:
    """Application factory."""
    app = web.Application()

    # Create an aiohttp.ClientSession for our application
    app_client = ClientSession()
    app['app_client'] = app_client

    # Create a Twilio REST client for sending SMS
    twilio_account_sid = os.environ['TWILIO_ACCOUNT_SID']
    twilio_auth_token = os.environ['TWILIO_AUTH_TOKEN']
    twilio_client = Client(twilio_account_sid, twilio_auth_token)
    app['twilio_client'] = twilio_client
    app['convos'] = {}

    # Initialize Returnzero token
    jwt_token = init_rtzr()
    app['rtzr_token'] = jwt_token

    # Store the ElevenLabs API key directly in the app dictionary
    app['elevenlabs_api_key'] = os.getenv('ELEVENLABS_API_KEY')

    # Create a place for Returnzero responses to talk to REST handlers
    response_queues = {}
    app['response_queues'] = response_queues

    # Set up routing table
    app.add_routes(routes)

    # Initialize the SYSTEM_MESSAGE_CONTENT
    app['SYSTEM_MESSAGE_CONTENT'] = SYSTEM_MESSAGE_CONTENT

    return app


def init_rtzr():
    client_id = os.getenv('RETURNZERO_CLIENT_ID')
    client_secret = os.getenv('RETURNZERO_CLIENT_SECRET')

    auth_url = 'https://openapi.vito.ai/v1/authenticate'
    auth_data = {
        'client_id': client_id,
        'client_secret': client_secret
    }

    resp = requests.post(
        auth_url,
        data=auth_data
    )
    resp.raise_for_status()
    jwt_token = resp.json()['access_token']

    return jwt_token


if __name__ == "__main__":
    # clear transcript file
    with open('transcript.txt', 'w') as f:
        f.write('')
    load_dotenv()
    logging.basicConfig(level=logging.DEBUG)

    web.run_app(app_factory())
