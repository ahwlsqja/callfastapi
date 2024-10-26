import os
import torch
import transformers
from datasets import load_from_disk
from transformers import (
    BitsAndBytesConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TextStreamer,
    pipeline
)
from peft import (
    LoraConfig,
    prepare_model_for_kbit_training,
    get_peft_model,
    get_peft_model_state_dict,
    set_peft_model_state_dict,
    TaskType,
    PeftModel
)
from trl import SFTTrainer
import os

BASE_MODEL = "yanolja/EEVE-Korean-10.8B-v1.0"

model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, load_in_4bit=True, device_map="auto")
# model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, device_map={"": "cpu"})

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
print('Done1')
prompt = "한국의 아이돌 문화에 대해 알려줘."

# 텍스트 생성을 위한 파이프라인 설정
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=256)
print('Done2')

try:
    outputs = pipe(
        prompt,
        do_sample=False,
        max_new_tokens=128,
        temperature=0.2,
        top_k=50,
        top_p=0.95,
        repetition_penalty=1.2,
        add_special_tokens=True
    )
    print('Done3')
except Exception as e:
    print(f'Exception Occurred: {e}')

print(outputs[0]["generated_text"][len(prompt):])