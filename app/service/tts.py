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

async def tts_stream_generator(voice_id: str):
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

                async for chunk in response.content.iter_chunked(1024):
                    if not chunk:
                        break
                    yield chunk

        except Exception as e:
            logging.error(f"Error while streaming TTS from ElevenLabs: {str(e)}")
            raise Exception(f"Error while streaming TTS from ElevenLabs: {str(e)}")