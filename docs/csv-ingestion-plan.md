# CSV Ingestion Pipeline - Complete Implementation Plan

**Status**: Ready for Coding Agent Implementation  
**Environment**: Kubernetes Cluster (Hanoi)  
**Date**: December 23, 2025

---

## 🎯 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER UPLOAD                                │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Server (Port 8000)                                         │
│  ├─ POST /upload/csv                                               │
│  ├─ Read CSV from request                                          │
│  ├─ Split into chunks (configurable size/rows)                     │
│  └─ Publish filenames to Kafka topic: "csv-ingestion"              │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  KAFKA BROKER  │
        │ Topic: csv-    │
        │ ingestion      │
        │ Partitions: 3  │
        └────────┬───────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Airflow DAG: csv-ingestion-listener                                │
│  ├─ AwaitMessageTriggerFunctionSensor                              │
│  │  └─ Listens to kafka topic: "csv-ingestion"                     │
│  └─ TriggerDagRunOperator                                          │
│     └─ Triggers NiFi ingestion processor                           │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NiFi Template: CSV to MinIO Ingestion                              │
│  ├─ InvokeHTTP Processor → Fetch CSV from API                      │
│  ├─ SplitContent (if needed)                                       │
│  ├─ PutS3Object Processor → Store in MinIO raw bucket              │
│  └─ LogAttribute + UpdateAttribute (tracking)                      │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  MINIO         │
        │  Bucket: raw   │
        │  Objects: CSV  │
        └────────────────┘
```

---

## 📋 Component Breakdown

### 1. **FastAPI Server** (New Development)

#### 1.1 Project Structure
```
fastapi-csv-uploader/
├── main.py                          # FastAPI app entry point
├── config.py                        # Configuration & env variables
├── services/
│   ├── csv_processor.py             # CSV chunking logic
│   ├── kafka_producer.py            # Kafka integration
│   └── file_manager.py              # Temporary file handling
├── models/
│   └── schemas.py                   # Pydantic schemas
├── requirements.txt
├── Dockerfile
└── kubernetes/
    ├── deployment.yaml
    ├── service.yaml
    └── configmap.yaml
```

#### 1.2 Key Features

**Endpoint: `POST /upload/csv`**
- Accept CSV file upload from client
- Parameters:
  - `file`: CSV file (multipart/form-data)
  - `chunk_size`: Optional, default 50MB
  - `chunk_type`: "size" (MB) | "rows" (number of rows) | "count" (fixed number of files)
  - `dataset_name`: Required, for tracking and organization

**Processing Logic:**
1. Validate file format and size
2. Read CSV streaming (don't load entire file into memory)
3. Split into chunks:
   - **By Size**: Read chunks of N MB, split on complete CSV rows
   - **By Rows**: Read line-by-line, group into N rows per file
   - **By Count**: Divide total rows by N, create that many files
4. Save chunks to temporary local storage (`/tmp/csv-chunks/`)
5. Generate filenames with pattern: `{dataset_name}_{chunk_id}_{timestamp}.csv`
6. Publish each filename + metadata to Kafka topic `csv-ingestion`
7. Return response with upload ID, total chunks, and tracking URL

**Response Format:**
```json
{
  "upload_id": "uuid-string",
  "dataset_name": "sales_data",
  "total_chunks": 5,
  "chunk_size": 50,
  "chunk_unit": "MB",
  "status": "processing",
  "tracking_url": "/uploads/{upload_id}/status",
  "created_at": "2025-12-23T11:17:00Z"
}
```

#### 1.3 Kafka Producer Configuration

**Topic: `csv-ingestion`**
- Partitions: 3 (for parallel processing)
- Replication Factor: 1
- Message Format:
  ```json
  {
    "upload_id": "uuid",
    "dataset_name": "sales_data",
    "chunk_id": 1,
    "filename": "sales_data_chunk_001_2025-12-23T11:17:00Z.csv",
    "chunk_size_mb": 50,
    "row_count": 10000,
    "file_path": "s3://raw-bucket/temp/sales_data_chunk_001_2025-12-23T11:17:00Z.csv",
    "headers": ["id", "name", "amount"],
    "published_at": "2025-12-23T11:17:30Z",
    "api_endpoint": "http://fastapi-csv-uploader:8000/chunks/{upload_id}/{chunk_id}/download"
  }
  ```

#### 1.4 Configuration (config.py)

```python
# Kafka Configuration
KAFKA_BROKER = "openhouse-kafka:9092"
KAFKA_TOPIC_INGEST = "csv-ingestion"
KAFKA_PARTITIONS = 3

# File Processing
CHUNK_SIZE_MB = 50  # Default chunk size
CHUNK_TYPE = "size"  # "size", "rows", or "count"
CHUNK_ROWS = 10000  # If chunk_type = "rows"
MAX_CHUNKS = 100  # If chunk_type = "count"
MAX_FILE_SIZE_MB = 5000  # Max 5GB upload

# Temporary Storage
TEMP_DIR = "/tmp/csv-chunks"
CLEANUP_AFTER_HOURS = 24  # Auto-cleanup old chunks

# API Configuration
API_HOST = "0.0.0.0"
API_PORT = 8000
```

#### 1.5 Implementation Details

**CSV Chunking Strategy** (csv_processor.py):
```python
async def split_csv_by_size(file: UploadFile, chunk_size_mb: int):
    """
    Stream large CSV file and split by file size
    - Read in chunks, split on complete CSV rows
    - Preserve headers in each chunk
    - Handle encoding issues
    """
    # Pseudo-code flow:
    # 1. Read first line (headers)
    # 2. While file not exhausted:
    #    - Read CHUNK_SIZE_MB
    #    - If split mid-row, backtrack to last complete row
    #    - Write headers + rows to new file
    #    - Increment chunk counter
    #    - Publish to Kafka
    
async def split_csv_by_rows(file: UploadFile, rows_per_chunk: int):
    """
    Stream CSV and group by row count
    - Read line-by-line
    - Group every N rows into a chunk file
    - Include headers in each chunk
    """

async def split_csv_by_count(file: UploadFile, num_chunks: int):
    """
    Read entire CSV (or estimate), divide into N equal parts
    - Count total rows or estimate from file size
    - Calculate rows_per_chunk = total_rows / num_chunks
    - Use split_csv_by_rows() with calculated value
    """
```

**Memory Efficiency:**
- Use `aiofiles` for async file operations
- Stream processing with fixed buffer size
- Never load entire CSV into memory
- Use `UploadFile.file.read(chunk_size)` for streaming

---

### 2. **Airflow DAG** (Existing Setup Enhancement)

#### 2.1 DAG: `csv-ingestion-listener`

**File**: `dags/csv_ingestion_listener_dag.py`

**DAG Configuration:**
```python
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime(2025, 12, 1),
    'email_on_failure': True,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'csv-ingestion-listener',
    default_args=default_args,
    description='Listen to Kafka CSV ingestion events and trigger NiFi',
    schedule_interval=None,  # Event-driven, not time-based
    is_paused_upon_creation=False,
    catchup=False,
    tags=['data-ingestion', 'csv', 'kafka'],
)
```

#### 2.2 Kafka Connection Setup (Airflow Admin)

**Connection ID**: `kafka_csv_ingestion`
- Connection Type: Kafka
- Host: `openhouse-kafka`
- Port: `9092`
- Schema: (leave empty)
- Extra: `{"bootstrap_servers": "openhouse-kafka:9092"}`

#### 2.3 DAG Tasks

**Task 1: Listen to Kafka Topic**
```python
from airflow.providers.apache.kafka.sensors.kafka import AwaitMessageTriggerFunctionSensor
from airflow.models import Variable

def listen_for_csv_messages(message_content):
    """
    Callback function to evaluate Kafka message
    Returns True if message should trigger DAG
    """
    import json
    
    try:
        msg = json.loads(message_content)
        # Validate message has required fields
        required_fields = ['upload_id', 'filename', 'dataset_name']
        if all(field in msg for field in required_fields):
            print(f"✓ Valid message received: {msg['filename']}")
            return msg  # Return parsed message for downstream tasks
        return None
    except json.JSONDecodeError:
        return None

listen_task = AwaitMessageTriggerFunctionSensor(
    task_id='listen_kafka_csv_topic',
    kafka_conn_id='kafka_csv_ingestion',
    topic='csv-ingestion',
    event_triggered_function='dags.csv_ingestion_listener_dag.listen_for_csv_messages',
    poll_timeout=10,
    poll_interval=5,
    poke_interval=10,
    deferrable=True,  # Non-blocking
    tags=['sensor', 'kafka'],
)
```

**Task 2: Extract Message Data**
```python
from airflow.operators.python import PythonOperator
from airflow.models import Variable

def extract_kafka_message(**context):
    """Extract message from XCom and parse into variables"""
    message = context['task_instance'].xcom_pull(
        task_ids='listen_kafka_csv_topic'
    )
    
    if message:
        msg_data = json.loads(message)
        # Store in XCom for downstream tasks
        context['task_instance'].xcom_push(
            key='upload_id',
            value=msg_data.get('upload_id')
        )
        context['task_instance'].xcom_push(
            key='filename',
            value=msg_data.get('filename')
        )
        context['task_instance'].xcom_push(
            key='dataset_name',
            value=msg_data.get('dataset_name')
        )
        context['task_instance'].xcom_push(
            key='api_endpoint',
            value=msg_data.get('api_endpoint')
        )
        
        return msg_data
    
    raise ValueError("No valid message received from Kafka")

extract_task = PythonOperator(
    task_id='extract_message_data',
    python_callable=extract_kafka_message,
    provide_context=True,
    trigger_rule='all_done',
)
```

**Task 3: Trigger NiFi Process Group**
```python
from airflow.operators.http import SimpleHttpOperator
from airflow.models import Variable
import json

def prepare_nifi_request(**context):
    """Prepare NiFi API request with Kafka message data"""
    
    # Get data from previous task
    ti = context['task_instance']
    upload_id = ti.xcom_pull(task_ids='extract_message_data', key='upload_id')
    filename = ti.xcom_pull(task_ids='extract_message_data', key='filename')
    dataset_name = ti.xcom_pull(task_ids='extract_message_data', key='dataset_name')
    api_endpoint = ti.xcom_pull(task_ids='extract_message_data', key='api_endpoint')
    
    # Prepare NiFi request body
    nifi_request = {
        'upload_id': upload_id,
        'filename': filename,
        'dataset_name': dataset_name,
        'source_api': api_endpoint,
        'destination_bucket': 'raw',
        'destination_path': f'{dataset_name}/{filename}',
        'timestamp': datetime.utcnow().isoformat(),
    }
    
    # Save to XCom for HTTP operator
    context['task_instance'].xcom_push(
        key='nifi_request_body',
        value=json.dumps(nifi_request)
    )
    
    return nifi_request

prepare_nifi_task = PythonOperator(
    task_id='prepare_nifi_request',
    python_callable=prepare_nifi_request,
    provide_context=True,
)

# Trigger NiFi Process Group via REST API
trigger_nifi_task = SimpleHttpOperator(
    task_id='trigger_nifi_ingestion',
    method='PUT',
    http_conn_id='nifi_rest_api',  # Need to create this connection
    endpoint='nifi-api/process-groups/{pg-id}/run',  # Replace with actual PG ID
    data='{{ task_instance.xcom_pull(task_ids="prepare_nifi_request", key="nifi_request_body") }}',
    headers={'Content-Type': 'application/json'},
    log_response=True,
    do_xcom_push=True,
    trigger_rule='all_done',
)
```

**Task 4: Monitor NiFi Execution** (Optional)
```python
def monitor_nifi_status(**context):
    """Poll NiFi API to check if ingestion completed"""
    import time
    import requests
    
    ti = context['task_instance']
    upload_id = ti.xcom_pull(task_ids='extract_message_data', key='upload_id')
    
    nifi_host = Variable.get('nifi_api_host', 'openhouse-nifi:8443')
    pg_id = Variable.get('nifi_process_group_id')  # Store in Airflow Variables
    
    max_retries = 60
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Check NiFi process group status
            response = requests.get(
                f'https://{nifi_host}/nifi-api/process-groups/{pg_id}',
                verify=False,
                headers={'X-Request-Id': upload_id}
            )
            
            if response.status_code == 200:
                status = response.json().get('processGroupFlow', {}).get('flow', {}).get('stats', {})
                if status.get('bytesOutput') > 0:
                    print(f"✓ Ingestion completed: {status['bytesOutput']} bytes written")
                    return {'status': 'completed', 'upload_id': upload_id}
            
            time.sleep(10)
            retry_count += 1
        
        except Exception as e:
            print(f"Error checking NiFi status: {e}")
            retry_count += 1
    
    raise TimeoutError(f"NiFi ingestion timeout for upload: {upload_id}")

monitor_nifi_task = PythonOperator(
    task_id='monitor_nifi_status',
    python_callable=monitor_nifi_status,
    provide_context=True,
    trigger_rule='all_done',
    pool='nifi_monitoring',  # Limit concurrent monitoring tasks
)
```

#### 2.4 DAG Dependencies

```python
listen_task >> extract_task >> prepare_nifi_task >> trigger_nifi_task >> monitor_nifi_task
```

---

### 3. **NiFi Template** (New Configuration)

#### 3.1 NiFi Process Group Setup

**Name**: `csv-ingestion-raw-to-minio`  
**Version**: 1.0  
**Flow File Concurrency**: Enabled (for parallel chunk processing)

#### 3.2 Processors and Configuration

**Processor 1: ListenHTTP (Entry Point)**
```
Listening Port: 10000
Path: /csv-ingest
HTTP Method(s): POST
```
- Receives HTTP requests from Airflow
- Extracts upload metadata from request body
- Outputs FlowFile with metadata as attributes

**Processor 2: ExtractText (Extract JSON Metadata)**
```
JSON Path Expressions:
  - $.upload_id → upload_id
  - $.filename → filename
  - $.dataset_name → dataset_name
  - $.source_api → source_api
  - $.destination_bucket → dest_bucket
  - $.destination_path → dest_path
```

**Processor 3: InvokeHTTP (Fetch CSV from FastAPI)**
```
HTTP Method: GET
Remote URL: ${source_api}
Connection Timeout: 30s
Read Timeout: 60s
Maximum Response Length: 5GB (5368709120 bytes)
Output Response Body: true
Add Response Headers: true
```
- Fetches CSV file from FastAPI `/chunks/{upload_id}/{chunk_id}/download`
- Handles streaming response
- Stores file content in FlowFile body

**Processor 4: UpdateAttribute (Add Metadata)**
```
Attributes:
  minio.bucket = ${dest_bucket}
  minio.object = ${dest_path}
  upload_id = ${upload_id}
  ingestion_timestamp = ${now()}
  source_system = fastapi
```

**Processor 5: PutS3Object (Write to MinIO)**
```
AWS Credentials Provider: IAM Credentials
Access Key ID: ${MINIO_ACCESS_KEY}
Secret Access Key: ${MINIO_SECRET_KEY}
Region: us-east-1
Bucket: ${minio.bucket}
Object Key: ${minio.object}
Endpoint Override URL: http://minio:9000/
S3 Signature Version: S3V4
Multi-part Upload Threshold: 100MB
Multi-part Upload Part Size: 50MB
Content Type: text/csv
```

**Processor 6: LogAttribute (Success Logging)**
```
Log Output When: Success
Log Message: ✓ Successfully ingested ${filename} to s3://${minio.bucket}/${minio.object}
Log Attributes: true
```
- Connects from PutS3Object success relationship

**Processor 7: UpdateAttribute (Error Logging)**
```
Attributes:
  error_timestamp = ${now()}
  processor_failed = true
Attributes to Delete: minio.object
```
- Connects from PutS3Object failure relationship

**Processor 8: LogAttribute (Failure Logging)**
```
Log Level: ERROR
Log Message: ✗ Failed to ingest ${filename}: ${error}
Log Attributes: true
```

#### 3.3 Data Flow Connections

```
ListenHTTP
    ↓
ExtractText
    ↓
InvokeHTTP → (Response)
    ↓
UpdateAttribute
    ↓
PutS3Object
    ├─ success → LogAttribute (success)
    └─ failure → UpdateAttribute (error) → LogAttribute (error)
```

#### 3.4 Controller Services Configuration

**DBCPConnectionPool (Optional, if using database)**
- Name: `CSV_DB_Connection`
- Database Connection URL: (if needed for metadata tracking)
- Driver Class: (e.g., PostgreSQL)

**StandardSSLContextService (For HTTPS to MinIO)**
- Name: `MinIO_SSL_Context`
- Truststore Filename: (if using self-signed certs)
- Truststore Password: (from Kubernetes secret)

---

### 4. **Kubernetes Deployments**

#### 4.1 FastAPI Server Deployment

**File**: `k8s/fastapi-csv-uploader-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-csv-uploader
  namespace: default
  labels:
    app: fastapi-csv-uploader
    version: v1
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: fastapi-csv-uploader
  template:
    metadata:
      labels:
        app: fastapi-csv-uploader
    spec:
      serviceAccountName: fastapi-csv-uploader
      containers:
      - name: api
        image: your-registry/fastapi-csv-uploader:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: KAFKA_BROKER
          valueFrom:
            configMapKeyRef:
              name: csv-uploader-config
              key: kafka_broker
        - name: KAFKA_TOPIC
          valueFrom:
            configMapKeyRef:
              name: csv-uploader-config
              key: kafka_topic
        - name: CHUNK_SIZE_MB
          valueFrom:
            configMapKeyRef:
              name: csv-uploader-config
              key: chunk_size_mb
        - name: MAX_FILE_SIZE_MB
          valueFrom:
            configMapKeyRef:
              name: csv-uploader-config
              key: max_file_size_mb
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi
        volumeMounts:
        - name: tmp-chunks
          mountPath: /tmp/csv-chunks
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: tmp-chunks
        emptyDir:
          sizeLimit: 50Gi  # Temporary storage for chunks
---
apiVersion: v1
kind: Service
metadata:
  name: fastapi-csv-uploader
  namespace: default
  labels:
    app: fastapi-csv-uploader
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
    name: http
  selector:
    app: fastapi-csv-uploader
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: csv-uploader-config
  namespace: default
data:
  kafka_broker: "openhouse-kafka:9092"
  kafka_topic: "csv-ingestion"
  chunk_size_mb: "50"
  chunk_type: "size"
  max_file_size_mb: "5000"
  temp_dir: "/tmp/csv-chunks"
```

#### 4.2 Airflow Configuration

**Add to Airflow Kubernetes Secret**:
```bash
kubectl create secret generic nifi-credentials \
  --from-literal=nifi-api-host=openhouse-nifi:8443 \
  --from-literal=nifi-process-group-id=<actual-pg-id> \
  -n airflow
```

**Add to Airflow Variables** (via UI or CLI):
```bash
airflow variables set nifi_api_host "openhouse-nifi:8443"
airflow variables set nifi_process_group_id "12345-abcde-67890"
airflow variables set minio_access_key "<access-key>"
airflow variables set minio_secret_key "<secret-key>"
```

**Add to Airflow Connections** (via UI):
- **Conn ID**: `nifi_rest_api`
- **Conn Type**: HTTP
- **Host**: `openhouse-nifi`
- **Port**: `8443`
- **Schema**: `https`

- **Conn ID**: `kafka_csv_ingestion`
- **Conn Type**: Kafka
- **Host**: `openhouse-kafka`
- **Port**: `9092`
- **Extra**: `{"bootstrap_servers": "openhouse-kafka:9092"}`

---

## 🔧 Implementation Roadmap

### Phase 1: FastAPI Server Development (Days 1-3)

**Deliverables:**
- [ ] FastAPI project skeleton with all dependencies
- [ ] CSV chunking service (all three splitting strategies)
- [ ] Kafka producer integration
- [ ] File validation and error handling
- [ ] Upload tracking/monitoring endpoint
- [ ] Unit tests for chunking logic
- [ ] Docker image & Kubernetes deployment manifests
- [ ] Health check endpoints (`/health`, `/ready`)

**Key Files to Create:**
```
├── main.py
├── config.py
├── services/csv_processor.py
├── services/kafka_producer.py
├── services/file_manager.py
├── models/schemas.py
├── tests/test_csv_processor.py
├── Dockerfile
├── requirements.txt
└── kubernetes/*.yaml
```

### Phase 2: Airflow DAG Implementation (Days 2-3)

**Deliverables:**
- [ ] Create `csv_ingestion_listener_dag.py`
- [ ] Kafka sensor configuration
- [ ] Message extraction & validation
- [ ] NiFi REST API integration
- [ ] Error handling & retry logic
- [ ] Monitoring task
- [ ] DAG unit tests
- [ ] Airflow connection setup

**Key Files to Create:**
```
dags/
├── csv_ingestion_listener_dag.py
├── modules/
│   ├── kafka_listener.py
│   ├── nifi_api_client.py
│   └── validators.py
└── tests/
    └── test_csv_ingestion_dag.py
```

### Phase 3: NiFi Template Setup (Days 2-3)

**Deliverables:**
- [ ] NiFi Process Group creation (`csv-ingestion-raw-to-minio`)
- [ ] All 8 processors configured
- [ ] Data flow connections
- [ ] SSL/TLS configuration for MinIO
- [ ] Test data flow end-to-end
- [ ] NiFi template export (for version control)
- [ ] Error handling flow for failed ingestions

**Configuration Files:**
```
nifi/
├── templates/
│   └── csv-ingestion-raw-to-minio.xml
├── controller-services/
│   └── minio-ssl-context.yaml
└── processors/
    ├── listen-http-config.yaml
    ├── invoke-http-config.yaml
    └── put-s3-object-config.yaml
```

### Phase 4: Integration Testing (Days 3-4)

**Deliverables:**
- [ ] End-to-end test CSV file (various sizes)
- [ ] Upload → Kafka → Airflow → NiFi → MinIO flow test
- [ ] Error scenario testing (network failures, large files, etc.)
- [ ] Load testing (concurrent uploads)
- [ ] Monitoring & logging validation
- [ ] Documentation & runbooks

**Test Scenarios:**
```
1. Small CSV (< 1MB)
2. Medium CSV (100MB)
3. Large CSV (1GB)
4. Multiple concurrent uploads
5. Network failure recovery
6. Invalid CSV format handling
7. Kafka consumer lag monitoring
8. NiFi processor failures
```

---

## 📊 Data Flow Specifications

### Message Format Examples

**Kafka Topic: `csv-ingestion`**

```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "dataset_name": "sales_transactions",
  "chunk_id": 1,
  "total_chunks": 5,
  "filename": "sales_transactions_chunk_001_2025-12-23T11:17:00Z.csv",
  "chunk_size_mb": 50,
  "row_count": 10000,
  "row_start": 1,
  "row_end": 10000,
  "file_path": "s3://raw-bucket/temp/sales_transactions_chunk_001_2025-12-23T11:17:00Z.csv",
  "headers": ["id", "customer_id", "amount", "timestamp"],
  "header_count": 4,
  "published_at": "2025-12-23T11:17:30Z",
  "api_endpoint": "http://fastapi-csv-uploader:8000/chunks/550e8400-e29b-41d4-a716-446655440000/1/download",
  "source_system": "fastapi",
  "version": "1.0"
}
```

**NiFi FlowFile Attributes** (after ingestion):
```
uuid = a1b2c3d4-e5f6-7890-abcd-ef1234567890
filename = sales_transactions_chunk_001_2025-12-23T11:17:00Z.csv
path = /
upload_id = 550e8400-e29b-41d4-a716-446655440000
dataset_name = sales_transactions
minio.bucket = raw
minio.object = sales_transactions/chunk_001/sales_transactions_chunk_001_2025-12-23T11:17:00Z.csv
ingestion_timestamp = 2025-12-23T11:17:45.123Z
source_system = fastapi
file_size = 52428800  (50MB)
mime_type = text/csv
```

---

## 🚨 Error Handling & Recovery

### FastAPI Server Error Cases

| Error | Handling |
|-------|----------|
| File too large (> 5GB) | Return 413 Payload Too Large |
| Invalid CSV format | Return 400 Bad Request with details |
| Kafka producer failure | Retry 3 times, then 500 Internal Server Error |
| Disk full in `/tmp` | Clean up oldest chunks, warn if < 1GB free |
| Memory pressure | Stream processing ensures constant memory usage |

### Airflow DAG Error Cases

| Error | Handling |
|-------|----------|
| Kafka consumer timeout | Retry sensor after 5 min, max 3 retries |
| NiFi API unreachable | Pause DAG, send alert, manual resume |
| Invalid Kafka message | Log error, skip message, continue listening |
| NiFi ingestion timeout | Fail task after 10 min, alert ops team |

### NiFi Processor Error Cases

| Error | Handling |
|-------|----------|
| HTTP 404 from FastAPI | Route to error queue, retry after 1 hour |
| MinIO connection failed | Route to error queue, alert ops, retry |
| Out of disk space in MinIO | Fail processor, alert storage team |
| Invalid credentials | Halt and notify, require manual fix |

### Recovery Procedures

```
1. **Automatic**:
   - Kafka offset reset if message fails 3 times
   - NiFi automatic retry with exponential backoff
   - FastAPI file cleanup after 24 hours

2. **Manual**:
   - Airflow: Resume DAG from last checkpoint
   - NiFi: Purge error queue, restart processor
   - MinIO: Check bucket permissions, verify space
```

---

## 📈 Monitoring & Observability

### Key Metrics to Track

**FastAPI Server:**
- Request count per endpoint
- Upload success/failure rate
- Average chunk processing time
- File size distribution
- Disk usage in `/tmp`
- Kafka publish latency

**Airflow DAG:**
- Kafka listener uptime
- Message consumption rate
- NiFi trigger success rate
- DAG run duration
- Error rates and types

**NiFi:**
- Processor queue depth
- Flow file throughput (files/sec)
- Bytes written to MinIO
- Error flow file count
- Controller service health

**MinIO:**
- Bucket size growth
- Object count
- Upload latency
- Storage utilization by dataset

### Logging Standards

**FastAPI:**
```python
import logging
logger = logging.getLogger(__name__)

# Log format
logger.info(f"[{upload_id}] Chunk {chunk_id}/{total_chunks}: {filename} processed")
logger.error(f"[{upload_id}] Kafka publish failed: {error}", exc_info=True)
```

**Airflow:**
```python
# Use built-in logging
self.log.info(f"Processing upload: {upload_id}")
self.log.error(f"NiFi API error: {response.status_code}")
```

**NiFi:**
- Use LogAttribute processor with structured format
- Include timestamp, upload_id, filename in all logs
- Route error logs to separate appender

---

## 🔐 Security Considerations

### API Security
- [ ] Implement API key authentication for `/upload/csv`
- [ ] Rate limiting (e.g., 10 uploads/min per user)
- [ ] Request size limits enforced at HTTP server level
- [ ] Input validation (CSV format, headers, etc.)

### Data Security
- [ ] Encrypt data in transit (HTTPS for FastAPI, TLS for Kafka)
- [ ] Encrypt data at rest in MinIO (enable SSE-C)
- [ ] Audit log all uploads (who, when, what)

### Infrastructure Security
- [ ] MinIO credentials in Kubernetes secrets, not config maps
- [ ] NiFi SSL/TLS certificates for API communication
- [ ] Kafka broker authentication (if enabled)
- [ ] Network policies to restrict inter-pod communication

---

## 📝 Testing Checklist

### Unit Tests
- [ ] CSV chunking by size, rows, and count
- [ ] Kafka message serialization
- [ ] File validation and error cases
- [ ] Airflow sensor callback logic

### Integration Tests
- [ ] Upload → Kafka → Consume flow
- [ ] NiFi template execution with real files
- [ ] MinIO object verification

### End-to-End Tests
- [ ] Small CSV (1MB) flow
- [ ] Large CSV (500MB) flow
- [ ] Multiple concurrent uploads
- [ ] Failure recovery

### Performance Tests
- [ ] Maximum throughput (MB/sec)
- [ ] Latency P50, P95, P99
- [ ] Memory usage under load
- [ ] Kafka consumer lag

---

## 📚 Additional Resources

### Documentation to Create
1. API endpoint reference (Swagger/OpenAPI)
2. Kafka message schema (Avro/Protobuf)
3. NiFi template deployment guide
4. Troubleshooting runbook
5. Capacity planning guide

### Libraries & Versions
```
FastAPI==0.109.0
uvicorn==0.27.0
aiofiles==23.2.1
kafka-python==2.0.2
python-multipart==0.0.6
pydantic==2.5.0

# Airflow
apache-airflow==2.7.0
apache-airflow-providers-kafka==1.3.0
apache-airflow-providers-http==4.7.0

# Kubernetes
kubernetes==28.0.0
```

---

## 🎬 Getting Started

**For Coding Agent:**

1. **Review this plan** for architecture understanding
2. **Start with FastAPI** (Phase 1) - it's independent
3. **Parallel work**: Start Airflow DAG (Phase 2) while FastAPI is in testing
4. **NiFi template**: Deploy after Kafka integration verified
5. **Integration testing**: Combine all components Phase 4
6. **Documentation**: Update as implementation progresses

**Quick Start Commands:**
```bash
# Clone/create project
git init fastapi-csv-uploader
cd fastapi-csv-uploader

# Create structure
mkdir -p services models kubernetes tests

# FastAPI development
pip install -r requirements.txt
uvicorn main:app --reload

# Deploy to Kubernetes
kubectl apply -f kubernetes/

# Monitor
kubectl logs -f deployment/fastapi-csv-uploader
kubectl port-forward svc/fastapi-csv-uploader 8000:8000
```

---

**Status**: Ready for implementation  
**Last Updated**: December 23, 2025  
**Contact**: For clarifications on architecture or requirements
