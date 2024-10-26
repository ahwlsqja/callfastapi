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

from .llama import get_chatgpt_response, call_chatgpt

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

async def handle_twilio_messages(call_sid_queue: asyncio.Queue, audio_queue: asyncio.Queue, twilio_ws: WebSocket):
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

async def stream_audio_to_rtzr(audio_queue: asyncio.Queue, rtzr_ws: ClientWebSocketResponse):
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
                response_queue.put_nowait('END_TRANSCRIPT_MARKER')
                break

        except Exception as e:
            logging.error(f"Error while receiving message from Returnzero WebSocket: {str(e)}")
            break