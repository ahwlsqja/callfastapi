from llama_cpp import Llama
from transformers import AutoTokenizer

model_id = 'MLP-KTLim/llama-3-Korean-Bllossom-8B-gguf-Q4_K_M'
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = Llama(
    model_path='model/bllossom/llama-3-Korean-Bllossom-8B-Q4_K_M.gguf',
    n_ctx=512,
    n_gpu_layers=-1        # Number of model layers to offload to GPU
)

PROMPT = \
'''
너는 누군가의 엄마야. 지금 5살 아들과 통화할거고 정확하고 친절하게 답변해야해. 아이가 어떤 상태인지 잘 알 수 있는 질문들을 많이해줘. 일단 여보세요?로 대화를 시작하고 짧고 간결하게 얘기해.
'''

instruction = ''

messages = [
    {"role": "system", "content": f"{PROMPT}"},
    {"role": "user", "content": f"{instruction}"}
    ]

prompt = tokenizer.apply_chat_template(
    messages, 
    tokenize = False,
    add_generation_prompt=True
)

generation_kwargs = {
    "max_tokens":512,
    "stop":["<|eot_id|>"],
    "top_p":0.9,
    "temperature":0.6,
    "echo":True, # Echo the prompt in the output
}

resonse_msg = model(prompt, **generation_kwargs)
print(f"Response! ::::::: {resonse_msg['choices'][0]['text'][len(prompt):]}")
