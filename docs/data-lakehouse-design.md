# Data Lakehouse Architecture với Kubernetes

## 📋 Mục Lục

1. [Tổng Quan Kiến Trúc](#1-tổng-quan-kiến-trúc)
2. [Các Thành Phần Chi Tiết](#2-các-thành-phần-chi-tiết)
3. [Data Flow](#3-data-flow)
4. [Triển Khai ArgoCD + Spark](#4-triển-khai-argocd--spark)
5. [Git Repository Structure](#5-git-repository-structure)
6. [Cài Đặt & Deployment](#6-cài-đặt--deployment)
7. [Monitoring & Troubleshooting](#7-monitoring--troubleshooting)

---

## 1. Tổng Quan Kiến Trúc

### 1.1 Kiến Trúc Tổng Thể

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Data Lakehouse Architecture                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL SERVICES                                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Keycloak   │  │   OpenFGA    │  │  Lakekeeper  │  │     MinIO    │   │
│  │ (Auth)       │  │ (AuthZ)      │  │ (Catalog)    │  │ (Storage)    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ KUBERNETES CLUSTER                                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ DATA INGESTION LAYER                                             │      │
│  ├──────────────────────────────────────────────────────────────────┤      │
│  │                                                                  │      │
│  │  ┌─────────────────────┐  ┌────────────────────────────────┐   │      │
│  │  │ Datasource API      │  │ Kafka Broker                   │   │      │
│  │  │ (Upload endpoint)   │  │ (Publish file metadata)        │   │      │
│  │  └────────┬────────────┘  └────────────────────────────────┘   │      │
│  │           │                          ▲                         │      │
│  │           │ upload file              │ subscribe               │      │
│  │           └──────────────────────────┘                         │      │
│  │                                                                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ ORCHESTRATION LAYER                                              │      │
│  ├──────────────────────────────────────────────────────────────────┤      │
│  │                                                                  │      │
│  │  ┌─────────────────────┐  ┌────────────────────────────────┐   │      │
│  │  │ Airflow DAG         │  │ NiFi Processor                 │   │      │
│  │  │ (Listener + Trigger)│  │ (Data Ingestion Flow)          │   │      │
│  │  └─────────────────────┘  └────────────────────────────────┘   │      │
│  │                                                                  │      │
│  │  1. Listen to Kafka                                            │      │
│  │  2. Trigger NiFi Flow                                          │      │
│  │  3. Push SparkApplication manifest to Git                      │      │
│  │  4. Trigger ArgoCD Sync                                        │      │
│  │  5. Monitor Spark Job                                          │      │
│  │                                                                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ DATA PROCESSING LAYER (GitOps Managed by ArgoCD)                │      │
│  ├──────────────────────────────────────────────────────────────────┤      │
│  │                                                                  │      │
│  │  ┌─────────────────────┐  ┌────────────────────────────────┐   │      │
│  │  │ Spark Operator      │  │ SparkApplication CRDs          │   │      │
│  │  │ (Job Manager)       │  │ (Bronze/Silver/Gold)           │   │      │
│  │  └─────────────────────┘  └────────────────────────────────┘   │      │
│  │           │                                                     │      │
│  │           │ Manages                                            │      │
│  │           ▼                                                     │      │
│  │  ┌─────────────────────────────────────────────────────────┐   │      │
│  │  │ Spark Driver + Executor Pods                            │   │      │
│  │  │ - Read from MinIO Raw Bucket                            │   │      │
│  │  │ - Transform data using Iceberg Catalog (Lakekeeper)    │   │      │
│  │  │ - Write to MinIO Warehouse (Bronze/Silver/Gold tables) │   │      │
│  │  └─────────────────────────────────────────────────────────┘   │      │
│  │                                                                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ CD/GITOPS LAYER                                                  │      │
│  ├──────────────────────────────────────────────────────────────────┤      │
│  │                                                                  │      │
│  │  ┌──────────────────────────────────────────────────────────┐   │      │
│  │  │ ArgoCD (GitOps Engine)                                   │   │      │
│  │  │ - Monitor Git Repo                                       │   │      │
│  │  │ - Sync SparkApplication manifests to K8s                │   │      │
│  │  │ - Self-heal & Automated rollback                        │   │      │
│  │  └──────────────────────────────────────────────────────────┘   │      │
│  │                                                                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ DATA STORAGE (Lakehouse)                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │ MinIO (Object Storage)                                          │       │
│  ├─────────────────────────────────────────────────────────────────┤       │
│  │                                                                 │       │
│  │  /raw          (Raw data - Parquet/JSON files)                │       │
│  │    ├── file_20250115_001.parquet                              │       │
│  │    ├── file_20250115_002.parquet                              │       │
│  │    └── ...                                                     │       │
│  │                                                                 │       │
│  │  /warehouse    (Iceberg Tables)                               │       │
│  │    ├── /bronze (Bronze Layer Tables)                          │       │
│  │    │   ├── raw_customers (Iceberg table)                      │       │
│  │    │   ├── raw_orders (Iceberg table)                         │       │
│  │    │   └── ...                                                 │       │
│  │    │                                                            │       │
│  │    ├── /silver (Silver Layer Tables)                          │       │
│  │    │   ├── customers_clean (Iceberg table)                    │       │
│  │    │   ├── orders_clean (Iceberg table)                       │       │
│  │    │   └── ...                                                 │       │
│  │    │                                                            │       │
│  │    └── /gold (Gold Layer Tables - Analytics Ready)            │       │
│  │        ├── customer_metrics (Iceberg table)                   │       │
│  │        ├── sales_dashboard (Iceberg table)                    │       │
│  │        └── ...                                                 │       │
│  │                                                                 │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│  Catalog Management:                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │ Lakekeeper (Iceberg REST Catalog)                              │       │
│  │ - Manages table metadata                                       │       │
│  │ - Version control & Time travel                               │       │
│  │ - Access control via OpenFGA                                  │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ GIT REPOSITORY (Single Source of Truth)                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  data-lakehouse-gitops/                                                    │
│  ├── spark-jobs/                                                           │
│  │   ├── bronze-layer/                                                    │
│  │   │   ├── jobs/                  ← Dynamic jobs (pushed by Airflow)   │
│  │   │   │   ├── bronze-dag-run-123.yaml                               │
│  │   │   │   ├── bronze-dag-run-124.yaml                               │
│  │   │   │   └── ...                                                    │
│  │   │   └── template.yaml          ← Base template                    │
│  │   ├── silver-layer/                                                   │
│  │   │   ├── jobs/                                                      │
│  │   │   └── template.yaml                                              │
│  │   └── gold-layer/                                                      │
│  │       ├── jobs/                                                       │
│  │       └── template.yaml                                               │
│  │                                                                        │
│  ├── argocd/                                                              │
│  │   ├── argocd-app.yaml            ← ArgoCD Application config        │
│  │   ├── argocd-cm.yaml             ← ArgoCD ConfigMap                 │
│  │   └── secret-refs.yaml           ← External Secrets                 │
│  │                                                                        │
│  └── airflow/                                                             │
│      ├── dags/                                                            │
│      │   └── data_ingestion_gitops.py  ← DAG push manifest to Git     │
│      └── docker/                                                          │
│          └── Dockerfile                                                   │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Stack Technology

| Component | Purpose | Version |
|-----------|---------|---------|
| **Kubernetes** | Container orchestration | 1.27+ |
| **MinIO** | Object storage (S3 compatible) | latest |
| **Apache Spark** | Distributed data processing | 3.3.0+ |
| **Spark Operator** | Spark job management on K8s | 1.2.0+ |
| **Apache NiFi** | Data ingestion & flow management | 1.18+ |
| **Apache Airflow** | Workflow orchestration | 2.5+ |
| **Apache Kafka** | Event streaming | 3.3+ |
| **Lakekeeper** | Iceberg REST Catalog | latest |
| **Apache Iceberg** | Lakehouse table format | 1.1+ |
| **Keycloak** | Authentication (OIDC) | 20+ |
| **OpenFGA** | Fine-grained authorization | 1.1+ |
| **ArgoCD** | GitOps CD tool | 2.8+ |

---

## 2. Các Thành Phần Chi Tiết

### 2.1 Datasource API (User Entry Point)

**Mục đích**: API endpoint cho user upload dữ liệu

```python
# datasource_api/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from kafka import KafkaProducer
import json
import os
from datetime import datetime

app = FastAPI(title="Datasource API")
kafka_producer = KafkaProducer(
    bootstrap_servers=os.getenv('KAFKA_BROKERS', 'kafka:9092'),
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

@app.post("/api/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    User upload file endpoint
    Payload: nhận file từ user
    Return: file metadata được gửi lên Kafka topic
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename required")
        
        # Create file metadata (không lưu file, chỉ lưu metadata)
        file_metadata = {
            "filename": file.filename,
            "size": file.size,
            "content_type": file.content_type,
            "timestamp": datetime.utcnow().isoformat(),
            "upload_id": f"{datetime.now().timestamp()}_{file.filename}"
        }
        
        # Publish file metadata to Kafka topic
        kafka_producer.send(
            'file-uploaded',
            value=file_metadata
        )
        kafka_producer.flush()
        
        return {
            "status": "success",
            "message": "File metadata published to Kafka",
            "file_metadata": file_metadata
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}
```

### 2.2 Apache Kafka (Event Bus)

**Mục đích**: Publish file metadata để Airflow lắng nghe

**Topic Definition:**
```yaml
# Kafka Topic: file-uploaded
Topic: file-uploaded
Partitions: 3
Replication Factor: 2
Retention: 7 days

Message Schema:
{
  "filename": "string",
  "size": "integer",
  "content_type": "string",
  "timestamp": "ISO8601",
  "upload_id": "string"
}
```

### 2.3 Apache NiFi (Data Ingestion)

**Mục đích**: Consume raw data từ sources và lưu vào MinIO raw bucket

```xml
<!-- NiFi Processor Group: RawDataIngestion -->
<!-- Diagram:
ListenHTTP 
  ↓
ConsumeFromKafka (file-uploaded topic)
  ↓
ValidateRecord
  ↓
PutS3Object (MinIO raw bucket)
  ↓
PublishKafkaRecord (raw-data-ready topic)
-->
```

**Key Processors:**
- **ConsumeKafka_2_6**: Consume file metadata từ Kafka
- **GetFile**: Fetch actual file data từ external source (HTTP/FTP/etc)
- **ValidateRecord**: Validate data format
- **PutS3Object**: Upload file to MinIO `s3://raw/` bucket
- **PublishKafka**: Publish "raw-data-ready" event

### 2.4 Apache Airflow (Orchestration)

**Mục đích**: Orchestrate entire workflow từ data ingestion đến spark processing

#### 2.4.1 DAG Structure

```python
# airflow/dags/data_ingestion_gitops.py
DAG: data_ingestion_gitops
Schedule: None (triggered by Kafka)
Description: End-to-end data ingestion to lakehouse

Tasks:
1. trigger_nifi_flow          (HttpOperator)
2. wait_raw_data_ready        (BashOperator)
3. push_sparkapp_to_git       (PythonOperator) ← Key task
4. trigger_argocd_sync        (BashOperator)
5. wait_spark_job_complete    (BashOperator)
```

#### 2.4.2 Kafka Listener Mechanism

```python
# Kafka listener for triggering DAG
from airflow.models import Variable
from kafka import KafkaConsumer
import json
import threading

class KafkaDAGTrigger:
    """
    Background thread that listens to Kafka
    and triggers Airflow DAG when new message arrives
    """
    
    def __init__(self):
        self.consumer = KafkaConsumer(
            'file-uploaded',
            bootstrap_servers=['kafka:9092'],
            group_id='airflow-dag-triggers',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
    
    def start_listening(self):
        """Start listening to Kafka messages"""
        for message in self.consumer:
            file_metadata = message.value
            # Trigger DAG with file_metadata as config
            self._trigger_dag(file_metadata)
    
    def _trigger_dag(self, file_metadata):
        """Trigger DAG via REST API"""
        from airflow.api.client.local_client import Client
        client = Client(None, None)
        client.trigger_dag(
            dag_id='data_ingestion_gitops',
            conf=file_metadata
        )

# Start listener in background thread
listener = KafkaDAGTrigger()
listener_thread = threading.Thread(target=listener.start_listening, daemon=True)
listener_thread.start()
```

### 2.5 Spark Operator (Job Execution)

**Mục đích**: Execute Spark jobs on Kubernetes

**Features:**
- Native Kubernetes integration
- Dynamic pod allocation
- Automatic driver/executor provisioning
- Status monitoring

### 2.6 ArgoCD (GitOps CD)

**Mục đích**: Sync SparkApplication manifests từ Git vào Kubernetes

**Key Features:**
- Automatic sync từ Git repository
- Self-healing (detect drift)
- Rollback via git revert
- Application health monitoring

### 2.7 External Services

#### Keycloak (Authentication)
```yaml
Used by:
- Datasource API: API authentication
- Lakekeeper: User authentication
- Airflow: DAG access control

Config:
OIDC realm: data-lakehouse
Client ID: datasource-api
Redirect URI: https://api.example.com/auth/callback
```

#### OpenFGA (Authorization)
```yaml
Used by:
- Lakekeeper: Table/schema access control
- Spark Jobs: Row/column level authorization

Model:
type user
type dataset
type role

relation member: user -> role
relation can_read: user -> dataset
relation can_write: user -> dataset
```

#### Lakekeeper (Iceberg Catalog)
```yaml
REST Endpoint: http://lakekeeper:8080
Warehouses:
- warehouse_name: prod
  location: s3a://warehouse/

Table Registration:
- Creates metadata in Lakekeeper
- References MinIO storage path
- Version control via Iceberg snapshots
```

---

## 3. Data Flow

### 3.1 End-to-End Flow Diagram

```
TIME: T0
┌────────────────────────────────────────────────────────────────┐
│ STEP 1: USER UPLOAD DATA                                       │
│                                                                │
│  User
│    │
│    ├─▶ POST /api/v1/upload
│    │   Datasource API
│    │     │
│    │     ├─ Parse file metadata
│    │     └─ Publish to Kafka (file-uploaded topic)
│    │
│  ✅ Response: File metadata published
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 1s
┌────────────────────────────────────────────────────────────────┐
│ STEP 2: AIRFLOW KAFKA LISTENER TRIGGERS                        │
│                                                                │
│  Kafka Consumer (Airflow)
│    │
│    ├─ Consume message from file-uploaded topic
│    ├─ Extract file metadata
│    └─ Trigger DAG: data_ingestion_gitops
│       Config:
│       {
│         "filename": "orders_20250115.csv",
│         "upload_id": "1234567890_orders_20250115.csv"
│       }
│
│  ✅ DAG Triggered
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 5s
┌────────────────────────────────────────────────────────────────┐
│ STEP 3: AIRFLOW TASK 1 - TRIGGER NIFI FLOW                    │
│                                                                │
│  Airflow DAG (Task: trigger_nifi_flow)
│    │
│    ├─ HttpOperator
│    │  Endpoint: NiFi REST API
│    │  Action: Start RawDataIngestion processor group
│    │
│    └─▶ NiFi Processor Group starts:
│          ├─ ConsumeKafka: Read raw file data
│          ├─ ValidateRecord: Validate format
│          ├─ Transform: Convert to Parquet
│          └─ PutS3Object: Upload to MinIO raw bucket
│                         Path: s3://raw/orders_20250115/
│
│  ✅ NiFi Flow Running
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 30s
┌────────────────────────────────────────────────────────────────┐
│ STEP 4: AIRFLOW TASK 2 - WAIT FOR RAW DATA                    │
│                                                                │
│  Airflow DAG (Task: wait_raw_data_ready)
│    │
│    ├─ BashOperator
│    │  Command: Check MinIO for raw data
│    │  Loop until:
│    │    └─ s3://raw/orders_20250115/data.parquet exists
│    │
│    ✅ Raw data ready in MinIO
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 35s
┌────────────────────────────────────────────────────────────────┐
│ STEP 5: AIRFLOW TASK 3 - PUSH SPARKAPP TO GIT (CRITICAL!)    │
│                                                                │
│  Airflow DAG (Task: push_sparkapp_to_git)
│    │
│    ├─ PythonOperator
│    │  Action:
│    │  1. Generate SparkApplication manifest from template
│    │  2. Fill in dynamic parameters:
│    │     - INPUT_PATH: s3://raw/orders_20250115/
│    │     - OUTPUT_PATH: s3://warehouse/bronze/
│    │     - JOB_ID: dag-run-id
│    │  3. Clone Git repo
│    │  4. Commit manifest to:
│    │     spark-jobs/bronze-layer/jobs/bronze-{job_id}.yaml
│    │  5. Push to Git main branch
│    │
│    └─▶ Git Repository Updated
│         Path: data-lakehouse-gitops
│         Branch: main
│         File added: spark-jobs/bronze-layer/jobs/bronze-dag-123.yaml
│
│  ✅ SparkApplication manifest in Git
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 40s
┌────────────────────────────────────────────────────────────────┐
│ STEP 6: ARGOCD DETECTS GIT CHANGE (AUTOMATIC)                │
│                                                                │
│  ArgoCD Controller
│    │
│    ├─ Monitor Git repo (default every 3 minutes or webhook)
│    ├─ Detect new commit in spark-jobs/bronze-layer/jobs/
│    └─ Calculate diff between Git and Kubernetes
│
│  Git vs Kubernetes:
│    Git:         bronze-dag-123.yaml (NEW)
│    Kubernetes:  (MISSING)
│    Status:      OutOfSync
│
│  ✅ Change Detected
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 45s
┌────────────────────────────────────────────────────────────────┐
│ STEP 7: ARGOCD SYNCS TO KUBERNETES                            │
│                                                                │
│  ArgoCD Sync Process
│    │
│    ├─ Read SparkApplication manifest from Git
│    ├─ kubectl apply -f bronze-dag-123.yaml
│    └─ Create SparkApplication CRD in data-platform namespace
│
│  Kubernetes Cluster:
│    SparkApplication: bronze-layer-dag-123
│    Status: SUBMITTED
│
│  ✅ SparkApplication created in K8s
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 50s
┌────────────────────────────────────────────────────────────────┐
│ STEP 8: SPARK OPERATOR PROVISIONS SPARK CLUSTER              │
│                                                                │
│  Spark Operator (watches SparkApplication CRDs)
│    │
│    ├─ Detect new SparkApplication
│    ├─ Create Driver Pod:
│    │  spark-driver-bronze-dag-123
│    │  Resources: 2 cores, 2Gi memory
│    │
│    └─ Create Executor Pods (3 instances):
│       spark-exec-1, spark-exec-2, spark-exec-3
│       Resources: 2 cores, 4Gi memory each
│
│  ┌─────────────────────────────────────┐
│  │ Kubernetes Pods Created             │
│  │ ├─ spark-driver-bronze-dag-123    │
│  │ ├─ spark-exec-1-bronze-dag-123    │
│  │ ├─ spark-exec-2-bronze-dag-123    │
│  │ └─ spark-exec-3-bronze-dag-123    │
│  └─────────────────────────────────────┘
│
│  Status: RUNNING
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 60s
┌────────────────────────────────────────────────────────────────┐
│ STEP 9: SPARK JOB EXECUTES (BRONZE TRANSFORMATION)           │
│                                                                │
│  Spark Driver (bronze-dag-123)
│    │
│    ├─ Load authentication from Keycloak
│    ├─ Connect to Lakekeeper (Iceberg Catalog)
│    │  Catalog URI: http://lakekeeper:8080
│    │
│    ├─ Read from MinIO Raw:
│    │  Path: s3://raw/orders_20250115/data.parquet
│    │  Records: 1,000,000
│    │
│    ├─ BRONZE Layer Transformation:
│    │  - Data type validation
│    │  - Null value handling
│    │  - Column naming standardization
│    │  - Add metadata columns (loaded_at, source, etc)
│    │
│    ├─ Write to MinIO Warehouse (Iceberg Table):
│    │  Table: bronze.raw_orders
│    │  Format: Iceberg
│    │  Location: s3://warehouse/bronze/raw_orders/
│    │  Version: v1
│    │
│    └─ Register table in Lakekeeper:
│       Table Name: raw_orders
│       Schema: (order_id, customer_id, amount, loaded_at, ...)
│       Properties: (Iceberg snapshots, partition spec, etc)
│
│  Progress:
│  ├─ Read:  100%
│  ├─ Transform: 100%
│  └─ Write: 100%
│
│  ✅ Bronze Layer Complete
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 120s
┌────────────────────────────────────────────────────────────────┐
│ STEP 10: AIRFLOW TASK 4 - WAIT FOR SPARK JOB                 │
│                                                                │
│  Airflow DAG (Task: wait_spark_complete)
│    │
│    ├─ BashOperator
│    │  Command: Monitor SparkApplication status
│    │  Loop until: status.applicationState.state == "COMPLETED"
│    │
│    ✅ Spark job completed
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 125s
┌────────────────────────────────────────────────────────────────┐
│ STEP 11: SILVER LAYER TRANSFORMATION (OPTIONAL)              │
│                                                                │
│  If configured:
│    ├─ Similar flow to Bronze
│    ├─ Read from bronze.raw_orders table
│    ├─ SILVER Layer Transformations:
│    │  - Remove duplicates
│    │  - Business logic enrichment
│    │  - Data quality checks
│    │
│    └─ Write to silver.customers, silver.orders tables
│
│  ✅ Silver Layer Complete
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 150s
┌────────────────────────────────────────────────────────────────┐
│ STEP 12: GOLD LAYER TRANSFORMATION (OPTIONAL)                │
│                                                                │
│  ├─ Read from silver tables
│  ├─ GOLD Layer (Analytics Ready):
│  │  - Aggregated metrics
│  │  - Pre-built dashboards
│  │  - Business KPIs
│  │
│  └─ Write to gold.customer_metrics, gold.sales_dashboard tables
│
│  ✅ All Layers Complete
│
└────────────────────────────────────────────────────────────────┘

TIME: T0 + 155s
┌────────────────────────────────────────────────────────────────┐
│ FINAL STATE: DATA LAKEHOUSE READY                             │
│                                                                │
│  MinIO Warehouse Structure:
│  /warehouse
│  ├── /bronze
│  │   ├── raw_orders/     ← Loaded & transformed
│  │   └── raw_customers/  ← Loaded & transformed
│  │
│  ├── /silver
│  │   ├── customers/      ← Cleaned & enriched
│  │   └── orders/         ← Cleaned & enriched
│  │
│  └── /gold
│      ├── customer_metrics/    ← Aggregated
│      └── sales_dashboard/     ← Pre-built
│
│  Lakekeeper Catalog:
│  └── Tables registered with Iceberg metadata
│      - Version history maintained
│      - Time travel enabled
│      - Access control via OpenFGA
│
│  ✅ WORKFLOW COMPLETE - Data ready for analytics!
│
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Git Flow trong Kiến Trúc

```
                 Developer / CI
                      │
                      │ Write code
                      ▼
        ┌───────────────────────────┐
        │ Git Repository (Main)     │
        │                           │
        │ spark-jobs/               │
        │ ├── bronze-layer/         │
        │ │   └── jobs/             │
        │ │       ├── bronze-123.yaml
        │ │       ├── bronze-124.yaml
        │ │       └── bronze-125.yaml
        │ └── argocd/               │
        │     └── argocd-app.yaml   │
        └───────────────────────────┘
                      ▲
                      │ Git push
                      │
        ┌───────────────────────────┐
        │ Airflow Task 3            │
        │ push_sparkapp_to_git      │
        │                           │
        │ Actions:                  │
        │ 1. Clone repo             │
        │ 2. Generate YAML          │
        │ 3. Commit manifest        │
        │ 4. Push to main           │
        └───────────────────────────┘
                      ▲
                      │ Manifest generated
                      │
        ┌───────────────────────────┐
        │ Airflow DAG Execution     │
        │                           │
        │ Task 1: Trigger NiFi      │
        │ Task 2: Wait Raw Data     │
        │ Task 3: Push to Git ◄──┐  │
        │ Task 4: Sync ArgoCD  │  │
        │ Task 5: Monitor Job  │  │
        └──────────────────────┘  │
                      ▲           │
                      │           │
                      └───────────┘
```

---

## 4. Triển Khai ArgoCD + Spark

### 4.1 ArgoCD Flow Chi Tiết

```
Git Repository (Source of Truth)
        │
        │ Webhook / Polling (every 3min)
        ▼
┌─────────────────────────────────┐
│ ArgoCD Application Controller    │
│                                 │
│ Monitor:                        │
│ - Git repo: main branch         │
│ - Path: spark-jobs/bronze-layer/
│ - Files: *.yaml                 │
└─────────────────────────────────┘
        │
        │ Detect new/changed manifest
        ▼
┌─────────────────────────────────┐
│ Diff Calculator                 │
│                                 │
│ Compare:                        │
│ Git:        bronze-123.yaml     │
│ Kubernetes: (missing)           │
│                                 │
│ Status: OutOfSync               │
└─────────────────────────────────┘
        │
        │ Auto sync (if enabled)
        ▼
┌─────────────────────────────────┐
│ Kubernetes API                  │
│                                 │
│ kubectl apply -f bronze-123.yaml│
│                                 │
│ Create SparkApplication CRD:    │
│ - Name: bronze-layer-123       │
│ - Namespace: data-platform     │
│ - Spec: From Git manifest      │
└─────────────────────────────────┘
        │
        │ CRD created
        ▼
┌─────────────────────────────────┐
│ Spark Operator (watches CRD)    │
│                                 │
│ Actions:                        │
│ 1. Detect new SparkApplication │
│ 2. Validate spec                │
│ 3. Create Driver Pod            │
│ 4. Create Executor Pods (3x)    │
│ 5. Monitor execution            │
└─────────────────────────────────┘
        │
        │ Pods created
        ▼
┌─────────────────────────────────┐
│ Kubernetes Scheduler            │
│                                 │
│ Actions:                        │
│ 1. Schedule pods to nodes       │
│ 2. Pull docker images           │
│ 3. Start containers             │
│ 4. Mount volumes (MinIO creds)  │
└─────────────────────────────────┘
        │
        │ Containers started
        ▼
┌─────────────────────────────────┐
│ Spark Job Execution             │
│                                 │
│ Driver Pod:                     │
│ - Load Spark config             │
│ - Connect to Lakekeeper         │
│ - Read from MinIO               │
│ - Coordinate executors          │
│ - Write results                 │
│                                 │
│ Executor Pods (3x):             │
│ - Process partitions in parallel│
│ - Push data to driver           │
│ - Return results                │
└─────────────────────────────────┘
        │
        │ Job completed
        ▼
┌─────────────────────────────────┐
│ Iceberg Tables                  │
│                                 │
│ MinIO Warehouse:                │
│ s3://warehouse/bronze/          │
│ └── raw_orders/                 │
│     ├── metadata/               │
│     └── data/                   │
│                                 │
│ Lakekeeper Catalog:             │
│ - Table: bronze.raw_orders      │
│ - Version: 1                    │
│ - Snapshots: metadata cached    │
└─────────────────────────────────┘
```

### 4.2 Git Repository Structure

```
data-lakehouse-gitops/
│
├── README.md
├── .gitignore
│
├── spark-jobs/                          # ← Main focus for ArgoCD
│   ├── kustomization.yaml               # Base Kustomize config
│   │
│   ├── bronze-layer/
│   │   ├── template.yaml                # Template (not deployed directly)
│   │   ├── values.yaml                  # Default values
│   │   ├── kustomization.yaml           # Kustomize overlay
│   │   │
│   │   └── jobs/                        # ← Dynamic jobs pushed by Airflow
│   │       ├── bronze-dag-run-123.yaml
│   │       ├── bronze-dag-run-124.yaml
│   │       └── bronze-dag-run-125.yaml
│   │
│   ├── silver-layer/
│   │   ├── template.yaml
│   │   ├── values.yaml
│   │   ├── kustomization.yaml
│   │   └── jobs/
│   │       ├── silver-dag-run-123.yaml
│   │       └── silver-dag-run-124.yaml
│   │
│   └── gold-layer/
│       ├── template.yaml
│       ├── values.yaml
│       ├── kustomization.yaml
│       └── jobs/
│           ├── gold-dag-run-123.yaml
│           └── gold-dag-run-124.yaml
│
├── argocd/                              # ArgoCD configs
│   ├── argocd-app.yaml                  # ArgoCD Application manifest
│   ├── argocd-appset.yaml               # Optional: ApplicationSet
│   ├── argocd-cm.yaml                   # ArgoCD ConfigMap
│   ├── argocd-rbac.yaml                 # RBAC policies
│   ├── notification-secret.yaml         # Notification configs
│   └── sync-strategy.yaml               # Advanced sync strategies
│
├── airflow/                             # Airflow DAG & configs
│   ├── dags/
│   │   ├── data_ingestion_gitops.py     # Main DAG
│   │   ├── spark_bronze_layer.py        # Bronze specific (optional)
│   │   └── utils/
│   │       ├── git_utils.py             # Git operations
│   │       └── k8s_utils.py             # K8s operations
│   │
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── config/
│       └── airflow.cfg
│
├── kubernetes/                          # K8s cluster configs
│   ├── namespaces/
│   │   ├── data-platform.yaml
│   │   ├── airflow.yaml
│   │   └── argocd.yaml
│   │
│   ├── secrets/
│   │   ├── minio-credentials.yaml
│   │   ├── github-token.yaml            # For Airflow to push to Git
│   │   ├── keycloak-credentials.yaml
│   │   └── lakekeeper-config.yaml
│   │
│   ├── rbac/
│   │   ├── spark-serviceaccount.yaml
│   │   └── airflow-rbac.yaml
│   │
│   └── configmaps/
│       ├── spark-config.yaml
│       └── nifi-config.yaml
│
├── helm/                                # Helm charts (optional)
│   ├── spark-operator/
│   ├── airflow/
│   └── argocd/
│
└── docs/
    ├── ARCHITECTURE.md
    ├── SETUP.md
    ├── TROUBLESHOOTING.md
    └── BACKUP_RESTORE.md
```

### 4.3 SparkApplication Manifest Template

```yaml
# spark-jobs/bronze-layer/template.yaml
# This is a TEMPLATE - Airflow will generate actual instances from this

apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: bronze-layer-{{ job_id }}        # Dynamically filled by Airflow
  namespace: data-platform
  labels:
    app: data-lakehouse
    layer: bronze
    job-id: "{{ job_id }}"
  annotations:
    argocd.argoproj.io/compare-result: "true"

spec:
  type: Python
  pythonVersion: "3"
  mode: cluster
  image: spark:3.3.0-scala2.12
  imagePullPolicy: IfNotPresent
  
  # Main Spark application
  mainApplicationFile: "s3a://spark-scripts/bronze_transform.py"
  
  # Script args - passed to main()
  arguments:
    - "--input-path"
    - "{{ input_path }}"        # Airflow fills: s3a://raw/file_name/
    - "--output-path"
    - "{{ output_path }}"       # Airflow fills: s3a://warehouse/bronze/
    - "--job-id"
    - "{{ job_id }}"
    - "--catalog-uri"
    - "{{ catalog_uri }}"       # Airflow fills: http://lakekeeper:8080
  
  sparkVersion: "3.3.0"
  
  # Restart policy for failures
  restartPolicy:
    type: OnFailure
    onFailureRetries: 2
    onFailureRetryInterval: 10
    onSubmissionFailureRetries: 1
    onSubmissionFailureRetryInterval: 20
  
  # Driver pod configuration
  driver:
    cores: 2
    memory: 2Gi
    memoryOverhead: 256m
    labels:
      version: v3.3.0
    serviceAccount: spark-operator
    
    # Environment variables from secrets
    env:
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: access-key
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: secret-key
      - name: KEYCLOAK_URL
        valueFrom:
          configMapKeyRef:
            name: external-services
            key: keycloak-url
    
    # Node affinity - run on specific nodes
    nodeSelector:
      workload: data-processing
    
    # Tolerations for taints
    tolerations:
      - key: "data-processing"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
  
  # Executor pod configuration
  executor:
    cores: 2
    instances: 3
    memory: 4Gi
    memoryOverhead: 512m
    
    env:
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: access-key
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: secret-key
    
    nodeSelector:
      workload: data-processing
    
    tolerations:
      - key: "data-processing"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
  
  # Spark configuration
  sparkConf:
    # Iceberg catalog configuration
    "spark.sql.warehouse.dir": "s3a://warehouse"
    "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog"
    "spark.sql.catalog.iceberg.type": "rest"
    "spark.sql.catalog.iceberg.uri": "{{ catalog_uri }}"
    "spark.sql.catalog.iceberg.s3.endpoint": "{{ minio_endpoint }}"
    
    # S3/MinIO configuration
    "spark.hadoop.fs.s3a.endpoint": "{{ minio_endpoint }}"
    "spark.hadoop.fs.s3a.access.key": "${MINIO_ACCESS_KEY}"
    "spark.hadoop.fs.s3a.secret.key": "${MINIO_SECRET_KEY}"
    "spark.hadoop.fs.s3a.path.style.access": "true"
    "spark.hadoop.fs.s3a.connection.ssl.enabled": "false"
    
    # Performance tuning
    "spark.sql.adaptive.enabled": "true"
    "spark.sql.adaptive.skewJoin.enabled": "true"
    "spark.sql.shuffle.partitions": "200"
    
    # Logging
    "spark.eventLog.enabled": "true"
    "spark.eventLog.dir": "s3a://spark-logs/events"
  
  # Hadoop configuration
  hadoopConf:
    "fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
  
  # Volumes and volume mounts
  volumes:
    - name: spark-scripts
      configMap:
        name: spark-bronze-scripts
    - name: py-requirements
      configMap:
        name: spark-requirements
  
  # Security context
  securityContext:
    runAsUser: 1000
    runAsGroup: 3000
    fsGroup: 2000
```

### 4.4 ArgoCD Application Manifest

```yaml
# argocd/argocd-app.yaml

apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: data-lakehouse-spark-jobs
  namespace: argocd
  
  # Finalizers ensure proper cleanup
  finalizers:
    - resources-finalizer.argocd.argoproj.io

spec:
  # ArgoCD project
  project: default
  
  # Source: Git repository
  source:
    repoURL: https://github.com/your-org/data-lakehouse-gitops.git
    targetRevision: main
    path: spark-jobs
    
    # Using Kustomize for manifest generation
    kustomize:
      version: v5.0.0
      # Don't automatically apply Kustomize
      # We manage kustomization.yaml explicitly
  
  # Destination: Kubernetes cluster
  destination:
    server: https://kubernetes.default.svc
    namespace: data-platform
  
  # Sync policy
  syncPolicy:
    # Automatic syncing
    automated:
      prune: true       # Delete K8s resources not in Git
      selfHeal: true    # Auto-sync when K8s drifts from Git
      allow:
        empty: false    # Prevent syncing empty repos
    
    # Sync options
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
    
    # Retry policy for failed syncs
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  
  # Ignore differences in status fields
  ignoreDifferences:
    - group: sparkoperator.k8s.io
      kind: SparkApplication
      jsonPointers:
        - /status              # Ignore status changes
        - /metadata/generation # Ignore generation changes
  
  # Health assessment
  statusBadgeEnabled: true
```

---

## 5. Cài Đặt & Deployment

### 5.1 Prerequisites

```bash
# Cluster requirements
- Kubernetes 1.27+
- kubectl configured
- Helm 3.10+
- Git account with token
- MinIO access credentials

# Tools needed
- git
- kubectl
- helm
- argocd CLI (optional)
- spark-submit (for local testing)
```

### 5.2 Installation Steps

#### Step 1: Create Kubernetes Namespaces

```bash
kubectl create namespace data-platform
kubectl create namespace argocd
kubectl create namespace airflow
kubectl create namespace spark-operator
```

#### Step 2: Install Spark Operator

```bash
helm repo add spark-operator https://googlecloudplatform.github.io/spark-on-k8s-operator
helm repo update

helm install spark-operator spark-operator/spark-operator \
  --namespace spark-operator \
  --set sparkJobNamespace=data-platform \
  --set enableWebhook=true
```

#### Step 3: Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=argocd-server \
  -n argocd --timeout=300s

# Get initial admin password
argocd admin initial-password -n argocd
```

#### Step 4: Configure ArgoCD Git Access

```bash
# Create GitHub token secret
kubectl create secret generic github-credentials \
  -n argocd \
  --from-literal=username=your-github-user \
  --from-literal=password=your-github-token

# Configure repository in ArgoCD
argocd repo add https://github.com/your-org/data-lakehouse-gitops.git \
  --username your-github-user \
  --password your-github-token
```

#### Step 5: Create Kubernetes Secrets

```bash
# MinIO credentials
kubectl create secret generic minio-credentials \
  -n data-platform \
  --from-literal=access-key=minioadmin \
  --from-literal=secret-key=minioadmin \
  --from-literal=endpoint=http://minio:9000

# GitHub token for Airflow to push
kubectl create secret generic github-push-token \
  -n airflow \
  --from-literal=token=your-github-token \
  --from-literal=user=your-github-user
```

#### Step 6: Install ArgoCD Application

```bash
kubectl apply -f argocd/argocd-app.yaml -n argocd

# Verify
kubectl get application -n argocd
kubectl get applications data-lakehouse-spark-jobs -n argocd -o yaml
```

#### Step 7: Install Airflow

```bash
# Using Helm
helm repo add apache-airflow https://airflow.apache.org
helm repo update

helm install airflow apache-airflow/airflow \
  -n airflow \
  -f airflow/values.yaml

# Or using Docker Compose for testing
docker-compose -f airflow/docker-compose.yaml up
```

#### Step 8: Deploy Kafka

```bash
# Simple Kafka using Docker Compose (for dev)
docker-compose -f kafka/docker-compose.yaml up

# Or using Helm (for production)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install kafka bitnami/kafka \
  -n data-platform \
  -f kafka/values.yaml
```

---

## 6. Monitoring & Troubleshooting

### 6.1 Monitoring Tools

#### Check ArgoCD Sync Status

```bash
# List all applications
kubectl get applications -n argocd

# Describe specific application
kubectl describe application data-lakehouse-spark-jobs -n argocd

# Watch sync status
kubectl get application data-lakehouse-spark-jobs \
  -n argocd -w -o json | jq '.status'

# ArgoCD UI
argocd login localhost:8080
argocd app get data-lakehouse-spark-jobs
```

#### Monitor Spark Jobs

```bash
# List SparkApplications
kubectl get sparkapplications -n data-platform

# Watch job status
kubectl get sparkapplication bronze-layer-dag-123 \
  -n data-platform -w -o json

# View pod logs
kubectl logs spark-driver-bronze-dag-123 -n data-platform
kubectl logs spark-exec-1-bronze-dag-123 -n data-platform

# Spark UI (port-forward)
kubectl port-forward spark-driver-bronze-dag-123 4040:4040 -n data-platform
# Access: http://localhost:4040
```

#### Monitor Airflow DAG

```bash
# Check DAG status
airflow dags list
airflow dags info data_ingestion_gitops

# Check DAG runs
airflow dags list-runs -d data_ingestion_gitops

# View task logs
airflow tasks log data_ingestion_gitops push_sparkapp_to_git 2025-01-15T10:00:00
```

### 6.2 Common Issues & Solutions

#### Issue 1: ArgoCD Not Syncing

```bash
# Check ArgoCD controller logs
kubectl logs -n argocd deployment/argocd-application-controller

# Manually trigger sync
argocd app sync data-lakehouse-spark-jobs

# Force sync
argocd app sync data-lakehouse-spark-jobs --force

# Check Git connection
argocd repo list
```

#### Issue 2: SparkApplication Stuck in SUBMITTED

```bash
# Check Spark Operator logs
kubectl logs -n spark-operator deployment/spark-operator

# Check Pod Events
kubectl describe pod spark-driver-bronze-dag-123 -n data-platform

# Check resource availability
kubectl describe nodes

# Check RBAC permissions
kubectl auth can-i create sparkapplications --as=system:serviceaccount:spark-operator:spark-operator
```

#### Issue 3: MinIO Connectivity Issues

```bash
# Test MinIO connectivity from pod
kubectl run -it --rm debug --image=minio/mc:latest -n data-platform -- \
  bash -c "mc alias set minio http://minio:9000 minioadmin minioadmin && mc ls minio/raw"

# Check credentials
kubectl get secret minio-credentials -n data-platform -o yaml
```

#### Issue 4: Iceberg Catalog Errors

```bash
# Test Lakekeeper connectivity
kubectl run -it --rm debug --image=curlimages/curl -n data-platform -- \
  curl http://lakekeeper:8080/api/v1/config

# Check table metadata
curl http://localhost:8080/api/v1/namespaces/bronze

# Verify table registration
spark-sql --packages org.apache.iceberg:iceberg-spark-runtime_2.12:1.1.0 \
  --conf spark.sql.catalog.iceberg=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.iceberg.type=rest \
  --conf spark.sql.catalog.iceberg.uri=http://lakekeeper:8080 \
  -e "USE iceberg; SHOW TABLES;"
```

### 6.3 Monitoring Dashboard Setup

#### Prometheus + Grafana for Spark Metrics

```yaml
# monitoring/prometheus-scrape-spark.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-spark-config
  namespace: monitoring
data:
  spark-targets.json: |
    [
      {
        "targets": ["spark-driver-*:4040"],
        "labels": {
          "job": "spark-driver",
          "application": "bronze-layer"
        }
      }
    ]
```

#### Alert Rules

```yaml
# monitoring/alert-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: spark-alerts
  namespace: monitoring
spec:
  groups:
    - name: spark.rules
      rules:
        - alert: SparkJobFailure
          expr: spark_app_state{state="FAILED"} == 1
          for: 5m
          annotations:
            summary: "Spark job {{ $labels.app }} failed"
        
        - alert: SparkExecutorDown
          expr: spark_executor_memory_used_bytes offset 5m - spark_executor_memory_used_bytes > 0
          for: 5m
          annotations:
            summary: "Spark executor {{ $labels.executor }} is down"
```

---

## 7. Best Practices & Recommendations

### 7.1 GitOps Best Practices

```yaml
# ✅ DO: Commit SparkApplication specs to Git
✓ Version control all configurations
✓ Use meaningful commit messages
✓ Require PR reviews for changes
✓ Tag releases for production deployments
✓ Keep Git repo as single source of truth

# ❌ DON'T: Apply K8s manifests directly
✗ kubectl apply -f sparkapp.yaml (directly to prod)
✗ Edit secrets directly in cluster
✗ Manual configuration changes
✗ Skip Git commit for quick fixes
```

### 7.2 Spark Job Best Practices

```python
# ✅ DO: Use Iceberg table format
✓ ACID transactions
✓ Time travel / snapshots
✓ Schema evolution
✓ Partition evolution

# ✅ DO: Optimize Spark configuration
✓ Proper partition count
✓ Enable adaptive query execution
✓ Tune memory allocation based on data size
✓ Use file format compression (Parquet)

# ✅ DO: Add data quality checks
✓ Validate record counts
✓ Check null percentages
✓ Validate data types
✓ Compare min/max values

# ❌ DON'T: Write directly to gold layer
✗ Skip intermediate layers (bronze/silver)
✗ Store raw data in gold
```

### 7.3 Security Best Practices

```yaml
# ✅ DO: Use Kubernetes Secrets for credentials
✓ Store credentials in K8s Secrets
✓ Use External Secrets Operator for encryption
✓ Enable RBAC for service accounts
✓ Use network policies to restrict traffic

# ✅ DO: Enable authentication & authorization
✓ Keycloak for API authentication
✓ OpenFGA for fine-grained access control
✓ Lakekeeper enforces table-level access

# ❌ DON'T: Hardcode credentials
✗ Credentials in code/configs
✗ Default passwords in production
✗ World-readable secrets
```

### 7.4 Performance Best Practices

```yaml
# ✅ DO: Use Kubernetes node pools
✓ Dedicated nodes for Spark jobs
✓ Use node selectors & taints/tolerations
✓ Reserve resources properly
✓ Use cluster autoscaling

# ✅ DO: Optimize data movement
✓ Partition data logically
✓ Use columnar formats (Parquet)
✓ Compress intermediate outputs
✓ Minimize network traffic

# ✅ DO: Monitor resource usage
✓ Set resource limits
✓ Monitor pod evictions
✓ Track disk I/O
✓ Alert on resource exhaustion
```

---

## 8. Conclusion

### 8.1 Architecture Summary

```
User Upload
    ↓
Datasource API + Kafka
    ↓
Airflow (Orchestration)
    ↓
    ├─ Trigger NiFi (Ingestion) → MinIO Raw Bucket
    │
    └─ Push SparkApplication to Git
         ↓
      ArgoCD (GitOps)
         ↓
      Kubernetes
         ↓
      Spark Operator
         ↓
      Spark Cluster
         ↓
      Transform Data
         ↓
      MinIO Warehouse (Iceberg Tables)
         ↓
      Ready for Analytics
```

### 8.2 Key Benefits

| Aspect | Benefit |
|--------|---------|
| **Scalability** | Kubernetes auto-scaling handles variable workloads |
| **Reliability** | Multi-replica setup with automatic failover |
| **Auditability** | Git history provides complete audit trail |
| **Recoverability** | Iceberg time-travel enables data rollback |
| **Flexibility** | Easy to add new transformation layers |
| **Cost Efficiency** | Use resources only when needed |
| **Compliance** | Fine-grained access control via OpenFGA |

### 8.3 Next Steps

1. **Setup Git Repository** - Clone template, customize for your org
2. **Deploy K8s Cluster** - Spin up Kubernetes (EKS/GKE/AKS)
3. **Install Components** - Follow installation steps in section 5
4. **Test Locally** - Use docker-compose for initial testing
5. **Setup CI/CD** - Configure GitHub Actions for automated testing
6. **Monitor & Alert** - Setup Prometheus + Grafana + PagerDuty
7. **Optimize** - Fine-tune resource allocations based on metrics
8. **Scale Out** - Add more executors, additional transformation layers

---

## References

- [Apache Iceberg Documentation](https://iceberg.apache.org/)
- [Spark Operator](https://github.com/GoogleCloudPlatform/spark-on-k8s-operator)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/overview/)
- [Apache Spark on Kubernetes](https://spark.apache.org/docs/latest/running-on-kubernetes.html)

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-15  
**Author**: Data Engineering Team
