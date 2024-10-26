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

BASE_MODEL = "MLP-KTLim/llama-3-Korean-Bllossom-8B"

starter = torch.cuda.Event(enable_timing=True)
ender = torch.cuda.Event(enable_timing=True)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
prompt = "안녕?"

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=256
)

with torch.no_grad():
    starter.record()

    try:
        outputs = pipe(
            prompt,
            do_sample=True,
            temperature=0.2,
            top_k=50,
            top_p=0.95,
            repetition_penalty=1.2,
            add_special_tokens=True
        )
    except Exception as e:
        print(f'Exception Occurred: {e}')
    
    ender.record()

infer_time = starter.elapsed_time(ender)
res = outputs[0]["generated_text"][len(prompt):]
print(f'Inference Time: {infer_time}\nResult: {res}')