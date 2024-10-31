# 1. Python 3.10 Alpine 베이스 이미지 사용
FROM python:3.10-alpine

# 2. 작업 디렉토리 설정
WORKDIR /usr/src/app

# 3. 종속성 설치에 필요한 기본 패키지 설치
RUN apk add --no-cache gcc musl-dev libffi-dev

# 4. requirements.txt 복사 및 패키지 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r ./requirements.txt

# 5. 애플리케이션 코드 복사
COPY app /usr/src/app/app

# 6. FastAPI 애플리케이션 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]