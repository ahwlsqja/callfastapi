# app/containers.py
from dependency_injector import containers, providers
import pika

import os
from dotenv import load_dotenv
load_dotenv()

RABBITMQ_CREDENTIAL1 = os.getenv('RABBITMQ_CREDENTIAL1')
RABBITMQ_CREDENTIAL2 = os.getenv('RABBITMQ_CREDENTIAL2')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_PORT = os.getenv('RABBITMQ_PORT')

class RabbitMQContainer(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["api"])  # 필요한 패키지 설정

    # RabbitMQ 연결을 Singleton으로 제공
    connection = providers.Singleton(
        pika.BlockingConnection,
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,  # NestJS에서 사용하는 RabbitMQ 인스턴스와 동일한 호스트
            port=RABBITMQ_PORT,
            credentials=pika.PlainCredentials(RABBITMQ_CREDENTIAL1, RABBITMQ_CREDENTIAL2)
        )
    )