# app/containers.py
from dependency_injector import containers, providers
import pika

class RabbitMQContainer(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["api"])  # 필요한 패키지 설정

    # RabbitMQ 연결을 Singleton으로 제공
    connection = providers.Singleton(
        pika.BlockingConnection,
        pika.ConnectionParameters(
            host="localhost",  # NestJS에서 사용하는 RabbitMQ 인스턴스와 동일한 호스트
            port=5672,
            credentials=pika.PlainCredentials("mo", "mo")
        )
    )