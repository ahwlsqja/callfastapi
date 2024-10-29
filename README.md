# Execute
```
uvicorn app.main:app --reload
```

## Installation
```
pip install fastapi
pip install "uvicorn[standard]"
pip install aiohttp
pip install python-dotenv
pip install twilio
pip install -U "huggingface_hub[cli]"
pip install transformers
pip install llama-cpp-python
```

## Project Architecture
##### 개발언어
- Python

##### 개발 툴
- VS Code

##### 프레임워크
- Fastapi
- Aiohttp

##### API
- 통화 인증 및 사용자 식별을 위해 PostgreSQL 사용
- 음성데이터 STT 수행을 위한 실시간 스트리밍 API Return Zero 사용
- 사용자 맞춤형 모델 QLoRa 어댑터를 불러오기 위해 AWS S3 사용
- text로 변환된 사용자 input 기반 개인화된 답변 생성을 위한 Llama3.1 + QLoRa 사용
- 생성된 답변 TTS 수행을 위한 API Elevenlabs 사용

##### 라이브러리
- fastapi
- twilio
- aiohttp
- torch
- transformers
- peft

##### 형상관리 도구
- Git