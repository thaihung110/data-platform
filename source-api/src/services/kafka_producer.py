import json
import logging

from config import settings
from confluent_kafka import Producer
from dto.schemas import KafkaMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaService:
    def __init__(self):
        conf = {
            "bootstrap.servers": settings.KAFKA_BROKER,
            "client.id": "fastapi-csv-uploader",
            "security.protocol": "SASL_PLAINTEXT",
            "sasl.mechanism": settings.KAFKA_SASL_MECHANISM,
            "sasl.username": settings.KAFKA_SASL_USERNAME,
            "sasl.password": settings.KAFKA_SASL_PASSWORD,
        }
        self.producer = Producer(conf)

    def delivery_report(self, err, msg):
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(
                f"Message delivered to {msg.topic()} [{msg.partition()}]"
            )

    def publish_chunk_metadata(self, message: KafkaMessage):
        try:
            payload = message.model_dump_json()
            self.producer.produce(
                settings.KAFKA_TOPIC_INGEST,
                key=message.upload_id,
                value=payload,
                callback=self.delivery_report,
            )
            # Flush to ensure delivery
            self.producer.poll(0)
        except Exception as e:
            logger.error(f"Error publishing to Kafka: {e}")

    def flush(self):
        self.producer.flush()


kafka_service = KafkaService()
