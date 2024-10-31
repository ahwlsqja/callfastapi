import asyncio
from contextlib import asynccontextmanager
import json
import logging
import threading
from aiohttp import ClientSession
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import pika
from app.router.router import router
from app.router.container import RabbitMQContainer


# from .service.data import 
# 전역 이벤트 루프 변수
global_event_loop = None

def get_or_create_event_loop():
    global global_event_loop
    if global_event_loop is None:
        global_event_loop = asyncio.get_event_loop()  # 현재 이벤트 루프 가져오기
        print(f"Created a new event loop with ID: {id(global_event_loop)}")
    else:
        print(f"Using existing event loop with ID: {id(global_event_loop)}")
    return global_event_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    global global_event_loop
    app.state.session = ClientSession()
    app.state.response_queues = {}
    app.state.convos = {}

    try:
        connection = RabbitMQContainer.connection()  # RabbitMQ 연결 가져오기
        app.state.rabbit_channel = connection.channel()  # 채널 생성

        try:
            app.state.rabbit_channel.queue_declare(queue='learntoservingqueue', passive=True)  # 큐가 존재하는지 확인
            print("learntoservingqueue already exists.")
        except pika.exceptions.ChannelClosed:
            app.state.rabbit_channel = connection.channel()
            app.state.rabbit_channel.queue_declare(queue='learntoservingqueue', durable=False)
            print("learntoservingqueue created.")
        except pika.exceptions.QueueNotFound:
    # 큐가 존재하지 않을 경우 생성
            app.state.rabbit_channel.queue_declare(queue='learntoservingqueue', durable=False)
            print("learntoservingqueue created.")

        # 응답 큐 생성

        # 이벤트 루프 생성
        get_or_create_event_loop()

        # 소비자 스레드 시작
        consumer_thread = threading.Thread(target=start_rabbitmq_consumer, args=(connection,))
        consumer_thread.start()

        yield  # 애플리케이션이 실행되는 동안 지속

    finally:
        await app.state.session.close()
        connection.close()  # 연결 종료
        
app = FastAPI(
    title='Leaning ML Server API',
    summary='its server',
    docs_url='/',
    lifespan=lifespan,
)


origins = ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)

    
def callback(ch, method, properties, body):
    # 수신한 메시지를 바이트에서 문자열로 디코딩
    decoded_body = body.decode('utf-8')
    print("Received message:", decoded_body)
    
    # JSON 형식으로 변환
    try:
        message = json.loads(decoded_body)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON: {e}")
        return

    # 모델 ID 추출
    model_id = message.get('model_id')
    if model_id is None:
        print("Model ID not found in the message.")
        return

    print(f"Model ID: {model_id}")

    # 여기서 모델 ID에 따라 로직 실행 (예: transcribe)
    # transcribe(model_id)와 같은 비즈니스 로직 추가 가능
    if model_id:
        print(f"Preparing to transcribe model ID: {model_id}")  # 추가 로그
        loop = get_or_create_event_loop()
        
        try:
            print(f"Calling transcribe for model ID: {model_id}")  # 호출 로그 추가
            

        except Exception as e:
            print(f"Error while running transcribe: {e}")
    # 응답을 datatolearnqueue로 전송
    response_message = {"status": "processing", "model_id": model_id}

    app.state.rabbit_channel.basic_publish(
        exchange='',
        routing_key='datatolearnqueue',
        body=json.dumps(response_message),
    )
    print(f"Response sent to datatolearnqueue: {response_message}")

            
def start_rabbitmq_consumer(connection):
    print("Starting RabbitMQ consumer...")
    try:
        channel = connection.channel()
        print("RabbitMQ connection established.")

        channel.basic_consume(queue='learntoservingqueue', on_message_callback=callback, auto_ack=True)
        print('Waiting for modelId messages. To exit press CTRL+C')
        channel.start_consuming()
    except Exception as e:
        print(f"Error establishing RabbitMQ connection: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)

