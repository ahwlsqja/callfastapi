import logging
import os

from llama_cpp import Llama
from transformers import AutoTokenizer

MODEL_PATH = './app/service/model/bllossom/'
MODEL_NAME = 'llama-3-Korean-Bllossom-8B-Q4_K_M.gguf'
MODEL_FULL_PATH = os.path.join(MODEL_PATH, MODEL_NAME)

DEFAULT_PROMPT = '''
    너는 누군가의 엄마야. 
    지금 5살 아들과 통화할거고 정확하고 친절하게 답변해야해. 
    아이가 어떤 상태인지 잘 알 수 있는 질문들을 많이해줘. 
    짧고 간결하게 얘기해.
'''
DEFAULT_INSTRUCTION = '일단 여보세요?로 대화를 시작해'

class LlamaChat:
    def __init__(self) -> None:
        self.check_if_model_exist()

        self.generation_kwargs = {
            "max_tokens":512,
            "stop":["<|eot_id|>"],
            "top_p":0.9,
            "temperature":0.6,
            "echo":True, # Echo the prompt in the output
        }

        model_id = 'MLP-KTLim/llama-3-Korean-Bllossom-8B-gguf-Q4_K_M'
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = Llama(
            model_path=MODEL_FULL_PATH,
            n_ctx=512,
            n_gpu_layers=-1 # Number of model layers to offload to GPU
        )

        self.conversations = {}

    def check_if_model_exist(self) -> None:
        if os.path.exists(MODEL_FULL_PATH):
            pass
        else:
            logging.info(f'No Model file found, downloding {MODEL_NAME}')
            try:
                os.system(f"huggingface-cli download MLP-KTLim/llama-3-Korean-Bllossom-8B-gguf-Q4_K_M --local-dir={MODEL_PATH}")
                logging.info(f'Downloaded {MODEL_NAME} successfully')
            except Exception as e:
                logging.error(f'An error has occurred while downloading {MODEL_NAME}\nError: {e}')

    def get_response(self, user_input: str, call_sid: str, is_new: bool = False,
                     prompt: str = DEFAULT_PROMPT, 
                     instruction: str = DEFAULT_INSTRUCTION) -> str:

        if is_new:
            if call_sid not in self.conversations:
                self.conversations[call_sid] = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": instruction}
                ]
            else:
                logging.warning(f'Call SID {call_sid} already has a conversation but is_new is set to True.')

        self.conversations[call_sid].append({"role": "user", "content": user_input})

        prompt = self.tokenizer.apply_chat_template(
            self.conversations[call_sid], 
            tokenize=False,
            add_generation_prompt=True
        )

        response_msg = self.model(prompt, **self.generation_kwargs)
        response = response_msg['choices'][0]['text'][len(prompt):]

        self.conversations[call_sid].append({"role": "assistant", "content": response})

        return response

# Test를 위해 직접 실행
if __name__ == '__main__':
    llama_chat = LlamaChat()

    first_response = llama_chat.get_response('여보세요?', '1', True)
    print(first_response)

    second_response = llama_chat.get_response('오늘 기분이 어때?', '2', True)
    print(second_response)

    third_response = llama_chat.get_response('안녕하세요?', '3', True)
    print(third_response)