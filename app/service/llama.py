import logging
import os
from fastapi import Request

SYSTEM_MESSAGE_CONTENT ="""
You are a bank representative. A customer has called with inquiries related to banking services. 
Guide the conversation by asking questions related to common banking services, such as account balance inquiries,
recent transaction history, loan eligibility, and credit card information. Respond briefly to the customer's answers 
and maintain a natural flow in the conversation. While waiting for the API response, keep prompting the customer with 
relevant questions and inform them appropriately when information is being checked or processed. Be courteous and 
provide a trustworthy experience. Always respond in Korean, using simple and clear language. Always answer in Korean
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



# import torch
# from transformers import (
#     BitsAndBytesConfig,
#     AutoModelForCausalLM,
#     AutoTokenizer,
#     pipeline
# )
# from peft import (
#     PeftModel,
#     PeftConfig
# )
# import torch
# from transformers import AutoModelForCausalLM, AutoTokenizer

# class LlamaQLoRa:
#     def __init__(self, model_id: str) -> None:
