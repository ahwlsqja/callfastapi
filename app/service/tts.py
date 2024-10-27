import logging
from aiohttp import ClientSession
async def tts_stream_generator(voice_id: str, request):
    headers = request.app.state.elevenlabs_headers
    payload = request.app.state.elevenlabs_voice_settings.copy()
    async with ClientSession() as session:
        try:
            async with session.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to stream TTS from ElevenLabs. Status: {response.status}")

                async for chunk in response.content.iter_chunked(1024):
                    if not chunk:
                        break
                    yield chunk

        except Exception as e:
            raise Exception(f"Error while streaming TTS from ElevenLabs: {str(e)}")