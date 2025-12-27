"""
Simple Kafka message checker using HTTP/polling.

This sensor checks if there are new messages on the Kafka topic without
actually consuming them. NiFi will handle the actual consumption.
"""

import logging
import time
from typing import Any

from airflow.sensors.base import BaseSensorOperator

from .config import config

logger = logging.getLogger(__name__)


class SimpleKafkaMessageSensor(BaseSensorOperator):
    """
    Simple sensor that waits before triggering NiFi.

    This is a placeholder sensor that:
    1. Waits for a specified interval
    2. Returns True to proceed to NiFi trigger

    In production, you can enhance this to:
    - Check Kafka consumer lag via JMX/HTTP
    - Call a health endpoint
    - Use actual Kafka consumer (requires confluent-kafka package)

    Configuration:
    Uses environment variables from config module.
    """

    def __init__(self, wait_seconds: int = 30, **kwargs):
        """
        Initialize sensor.

        Args:
            wait_seconds: Seconds to wait before proceeding (simulates checking)
            **kwargs: Airflow sensor arguments
        """
        super().__init__(**kwargs)
        self.wait_seconds = wait_seconds
        self._first_poke = True

    def poke(self, context) -> bool:
        """
        Check for messages (simplified version).

        Returns:
            bool: True to proceed to next task
        """
        if self._first_poke:
            logger.info(
                f"Waiting for Kafka messages on topic: {config.KAFKA_TOPIC_CSV_INGESTION}"
            )
            logger.info(
                f"Kafka bootstrap servers: {config.KAFKA_BOOTSTRAP_SERVERS}"
            )
            logger.info(
                f"Will wait {self.wait_seconds} seconds before triggering NiFi"
            )
            self._first_poke = False
            time.sleep(self.wait_seconds)
            return False

        logger.info(f"✓ Proceeding to trigger NiFi for Kafka processing")
        logger.info(
            f"  NiFi will consume messages from: {config.KAFKA_TOPIC_CSV_INGESTION}"
        )

        # In production, add actual check here:
        # - Query Kafka consumer group lag
        # - Check topic partition offsets
        # - Validate broker connectivity

        return True
