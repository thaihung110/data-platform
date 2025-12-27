"""
Airflow DAG to orchestrate Taxi Data Ingestion Spark Job

This DAG:
1. Triggers the taxi-data-ingestion SparkApplication on Kubernetes
2. Monitors the job execution
3. Runs hourly to process new taxi data from MinIO raw bucket to Iceberg bronze table
"""

from datetime import datetime, timedelta

from airflow.providers.cncf.kubernetes.operators.pod import (
    KubernetesPodOperator,
)
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import (
    SparkKubernetesSensor,
)
from kubernetes.client import models as k8s

from airflow import DAG

# Default arguments for the DAG
default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2025, 12, 25),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

# DAG definition
with DAG(
    dag_id="taxi-data-ingestion-spark",
    default_args=default_args,
    description="Hourly Spark job to ingest taxi data from MinIO raw to Iceberg bronze",
    schedule="@hourly",  # Run every hour
    catchup=False,
    tags=["data-ingestion", "spark", "taxi", "bronze"],
    max_active_runs=1,  # Prevent concurrent runs
) as dag:

    # Task 1: Apply SparkApplication manifest to Kubernetes
    submit_spark_job = KubernetesPodOperator(
        task_id="submit_taxi_ingestion_spark_job",
        name="taxi-ingestion-spark-submit",
        namespace="default",
        image="bitnamilegacy/kubectl:1.33.4-debian-12-r0",
        cmds=["kubectl"],
        arguments=[
            "apply",
            "-f",
            "/mnt/manifests/taxi-data-ingestion.yaml",
        ],
        volumes=[
            k8s.V1Volume(
                name="spark-manifests",
                config_map=k8s.V1ConfigMapVolumeSource(
                    name="spark-manifests",
                ),
            ),
        ],
        volume_mounts=[
            k8s.V1VolumeMount(
                name="spark-manifests",
                mount_path="/mnt/manifests",
                read_only=True,
            ),
        ],
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,  # Running inside Kubernetes cluster
        service_account_name="openhouse-spark-operator-spark",
    )

    # Task 2: Monitor SparkApplication until completion
    monitor_spark_job = SparkKubernetesSensor(
        task_id="monitor_taxi_ingestion_spark_job",
        namespace="default",
        application_name="taxi-data-ingestion",
        poke_interval=30,  # Check every 30 seconds
        timeout=3600,  # Timeout after 1 hour
        mode="poke",
        attach_log=True,
    )

    # Task 3: Cleanup - Delete SparkApplication after completion
    cleanup_spark_job = KubernetesPodOperator(
        task_id="cleanup_taxi_ingestion_spark_job",
        name="taxi-ingestion-spark-cleanup",
        namespace="default",
        image="bitnamilegacy/kubectl:1.33.4-debian-12-r0",
        cmds=["kubectl"],
        arguments=[
            "delete",
            "sparkapplication",
            "taxi-data-ingestion",
            "-n",
            "default",
            "--ignore-not-found=true",
        ],
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        service_account_name="openhouse-spark-operator-spark",
        trigger_rule="all_done",  # Run even if previous tasks fail
    )

    # Define task dependencies
    submit_spark_job >> monitor_spark_job >> cleanup_spark_job
