"""
Configuration module for CSV Ingestion pipeline.

All configuration is loaded from environment variables,
removing dependency on Airflow Connections and Variables.
"""

import os
from typing import Optional


class Config:
    """Centralized configuration from environment variables."""

    # ============================================================================
    # Kafka Configuration
    # ============================================================================

    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS", "openhouse-kafka:9092"
    )

    KAFKA_TOPIC_CSV_INGESTION: str = os.getenv(
        "KAFKA_TOPIC_CSV_INGESTION", "csv-ingestion"
    )

    KAFKA_CONSUMER_GROUP_ID: str = os.getenv(
        "KAFKA_CONSUMER_GROUP_ID", "airflow-csv-ingestion-consumer"
    )

    KAFKA_SASL_MECHANISM: str = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")

    KAFKA_SASL_USERNAME: str = os.getenv("KAFKA_SASL_USERNAME", "admin")

    KAFKA_SASL_PASSWORD: str = os.getenv("KAFKA_SASL_PASSWORD", "admin")

    KAFKA_SECURITY_PROTOCOL: str = os.getenv(
        "KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT"
    )

    KAFKA_AUTO_OFFSET_RESET: str = os.getenv(
        "KAFKA_AUTO_OFFSET_RESET", "latest"
    )

    KAFKA_POLL_TIMEOUT: int = int(os.getenv("KAFKA_POLL_TIMEOUT", "10"))

    KAFKA_POKE_INTERVAL: int = int(os.getenv("KAFKA_POKE_INTERVAL", "30"))

    KAFKA_SESSION_TIMEOUT_MS: int = int(
        os.getenv("KAFKA_SESSION_TIMEOUT_MS", "30000")
    )

    # ============================================================================
    # NiFi Configuration
    # ============================================================================

    NIFI_API_BASE_URL: str = os.getenv(
        "NIFI_API_BASE_URL", "https://openhouse-nifi:8443/nifi-api"
    )

    NIFI_PROCESS_GROUP_ID: str = os.getenv(
        "NIFI_PROCESS_GROUP_ID", "4be3c5be-019b-1000-4ef1-949cbb8c08de"
    )

    NIFI_VERIFY_SSL: bool = (
        os.getenv("NIFI_VERIFY_SSL", "false").lower() == "true"
    )

    NIFI_REQUEST_TIMEOUT: int = int(os.getenv("NIFI_REQUEST_TIMEOUT", "30"))

    @classmethod
    def get_kafka_consumer_config(cls) -> dict:
        """
        Get Kafka consumer configuration dictionary.

        Returns:
            dict: Kafka consumer configuration for confluent_kafka.Consumer
        """
        config = {
            "bootstrap.servers": cls.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": cls.KAFKA_CONSUMER_GROUP_ID,
            "auto.offset.reset": cls.KAFKA_AUTO_OFFSET_RESET,
            "enable.auto.commit": True,
            "session.timeout.ms": cls.KAFKA_SESSION_TIMEOUT_MS,
        }

        # Add SASL configuration if using SASL
        if "SASL" in cls.KAFKA_SECURITY_PROTOCOL:
            config.update(
                {
                    "security.protocol": cls.KAFKA_SECURITY_PROTOCOL,
                    "sasl.mechanism": cls.KAFKA_SASL_MECHANISM,
                    "sasl.username": cls.KAFKA_SASL_USERNAME,
                    "sasl.password": cls.KAFKA_SASL_PASSWORD,
                }
            )

        return config

    @classmethod
    def validate(cls) -> None:
        """
        Validate that required configuration is present.

        Raises:
            ValueError: If required configuration is missing
        """
        required_vars = [
            ("KAFKA_BOOTSTRAP_SERVERS", cls.KAFKA_BOOTSTRAP_SERVERS),
            ("NIFI_API_BASE_URL", cls.NIFI_API_BASE_URL),
            ("NIFI_PROCESS_GROUP_ID", cls.NIFI_PROCESS_GROUP_ID),
        ]

        missing = []
        for var_name, var_value in required_vars:
            if not var_value:
                missing.append(var_name)

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


# Global config instance
config = Config()
