from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kafka Configuration
    KAFKA_BROKER: str = "openhouse-kafka:9092"
    KAFKA_TOPIC_INGEST: str = "csv-ingestion"
    KAFKA_PARTITIONS: int = 3

    # Kafka SASL Authentication
    KAFKA_SASL_MECHANISM: str = "PLAIN"
    KAFKA_SASL_USERNAME: str = "admin"
    KAFKA_SASL_PASSWORD: str = "admin"

    # File Processing
    CHUNK_SIZE_MB: int = 50
    CHUNK_TYPE: str = "size"  # "size", "rows", or "count"
    CHUNK_ROWS: int = 10000
    MAX_CHUNKS: int = 100
    MAX_FILE_SIZE_MB: int = 5000

    # Temporary Storage
    TEMP_DIR: str = "/tmp/csv-chunks"
    CLEANUP_AFTER_HOURS: int = 24

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # External API Base URL (for NiFi to download chunks)
    # This should be the internal K8s service URL or external LoadBalancer URL
    BASE_URL: str = "http://fastapi-csv-uploader:8000"

    # Database Configuration
    DATABASE_HOST: str = "openhouse-postgresql-primary"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "source_api"
    DATABASE_USER: str = "source_api"
    DATABASE_PASSWORD: str = "source_api"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"

    class Config:
        # Environment variables are now read from Kubernetes ConfigMap
        # No need for .env file in containerized environments
        pass


settings = Settings()
