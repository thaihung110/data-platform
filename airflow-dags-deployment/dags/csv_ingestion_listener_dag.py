"""
CSV Ingestion Listener DAG

This DAG waits for Kafka messages then triggers NiFi to process them.

Workflow:
1. Sensor waits for messages on Kafka topic
2. Trigger NiFi process group
3. NiFi consumes messages from Kafka and processes CSV chunks

Note: Sensor only CHECKS for messages, NiFi handles actual consumption.

Configuration:
All configuration is loaded from environment variables (see .env.example).
No Airflow Connections or Variables are required.

Author: Data Engineering Team
Created: 2025-12-26
Updated: 2025-12-26 (Simplified sensor without confluent-kafka)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src directory to Python path for imports
dag_dir = Path(__file__).parent
src_dir = dag_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from airflow.operators.python import PythonOperator

# Local imports from src.ingestion
from ingestion.config import config
from ingestion.kafka_sensor import SimpleKafkaMessageSensor
from ingestion.nifi_client import trigger_nifi_process_group

# Airflow imports
from airflow import DAG

# DAG default arguments
default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2025, 12, 1),
    "email_on_failure": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
}

# Define the DAG
with DAG(
    dag_id="csv-ingestion-listener",
    default_args=default_args,
    description="Wait for Kafka messages then trigger NiFi processing (env var config)",
    schedule="@hourly",  # Check hourly, or set to None for manual trigger
    catchup=False,
    tags=["data-ingestion", "csv", "kafka", "nifi", "env-vars"],
) as dag:

    # Task 1: Wait for Kafka messages
    wait_for_kafka_task = SimpleKafkaMessageSensor(
        task_id="wait_for_kafka_messages",
        wait_seconds=30,  # Wait 30 seconds before proceeding
        poke_interval=60,  # Check every 60 seconds
        timeout=60 * 60 * 6,  # 6 hours timeout
        mode="poke",
        doc_md=f"""
        ## Wait for Kafka Messages
        
        This sensor waits before triggering NiFi to ensure messages are available.
        
        **Configuration** (from environment variables):
        - Kafka topic: `{config.KAFKA_TOPIC_CSV_INGESTION}`
        - Bootstrap servers: `{config.KAFKA_BOOTSTRAP_SERVERS}`
        
        **Note**: This is a simplified sensor. 
        For production, consider:
        - Installing `confluent-kafka` package
        - Using Airflow Kafka provider
        - Implementing actual topic offset checking
        
        **Current behavior**: Waits then proceeds to trigger NiFi
        """,
    )

    # Task 2: Trigger NiFi process group to consume and process
    trigger_nifi_task = PythonOperator(
        task_id="trigger_nifi_process_group",
        python_callable=trigger_nifi_process_group,
        retries=3,
        retry_delay=timedelta(minutes=1),
        doc_md=f"""
        ## Trigger NiFi Process Group
        
        Triggers NiFi to start consuming from Kafka and processing CSV chunks.
        
        **NiFi handles**:
        - Consuming messages from Kafka topic: `{config.KAFKA_TOPIC_CSV_INGESTION}`
        - Processing CSV chunks
        - Writing to MinIO/destination
        
        **Configuration** (from environment variables):
        - NiFi API URL: `{config.NIFI_API_BASE_URL}`
        - Process Group ID: `{config.NIFI_PROCESS_GROUP_ID}`
        - SSL Verification: `{config.NIFI_VERIFY_SSL}`
        
        **API Endpoint**: PUT /nifi-api/flow/process-groups/{{id}}
        """,
    )

    # Define task dependencies
    wait_for_kafka_task >> trigger_nifi_task
