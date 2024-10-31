import logging
import os
from fastapi import Request
from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()

OPENAI_MODEL_ID = os.getenv('OPENAI_MODEL_ID')

SYSTEM_MESSAGE_CONTENT ="""
You are an assistant tasked with providing engaging and relevant responses based on the given conversation context. Respond thoughtfully and appropriately to user inputs.
"""

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

    payload = {'model': OPENAI_MODEL_ID, 'messages': conversation}

    logging.info('Sending to ChatGPT -> User: %s', message)

    async with session.post(url, headers=headers, json=payload) as resp:
        if resp.status != 200:
            return ''
        resp_payload = await resp.json()
        response = resp_payload['choices'][0]['message']['content'].strip()

    conversation.append({'role': 'assistant', 'content': response})

    logging.info('ChatGPT: %s', response)

    return response
