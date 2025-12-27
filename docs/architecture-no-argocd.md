# Data Lakehouse Architecture Without ArgoCD
## Design, Flow & Implementation Plan

---

## 📋 Executive Summary

**Architecture:** Airflow + Kafka + NiFi + Spark + MinIO + Lakekeeper (NO ArgoCD)

**Core Flow:**
```
File Upload → Kafka → Airflow Listener
                        ├─ Task 1: Trigger NiFi via REST API
                        ├─ Task 2: Monitor NiFi ingestion
                        ├─ Task 3: Submit Spark job (raw → bronze)
                        └─ Task 4: Monitor Spark job completion
```

**Key Decision:** Airflow submits Spark jobs **directly via kubectl apply** (no Git, no ArgoCD)

---

## 1. Architecture Overview

### 1.1 System Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         USER LAYER                                  │
├────────────────────────────────────────────────────────────────────┤
│ • Web UI / API: File Upload Interface                              │
│ • Datasource API (FastAPI): Accept file uploads                    │
└────────────────────────┬───────────────────────────────────────────┘
                         │ HTTP POST /upload
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ ┌──────────────────┐     ┌──────────────────┐                     │
│ │  Apache Kafka    │────▶│  Airflow Listener│                     │
│ │  (Orchestration) │     │  (Trigger DAG)   │                     │
│ │                  │     └────────┬──────────┘                     │
│ │ Topics:          │              │                                │
│ │ • file-uploaded  │              ▼                                │
│ │ • raw-data-ready │     ┌─────────────────────┐                 │
│ └──────────────────┘     │   Airflow DAG       │                 │
│         ▲                │ (data_ingestion.py) │                 │
│         │                │                     │                 │
│ ┌───────┴──────────┐     │ Tasks:              │                 │
│ │  Datasource API  │     │ 1. trigger_nifi    │                 │
│ │  (FastAPI)       │     │ 2. wait_nifi_done  │                 │
│ │                  │     │ 3. submit_spark    │                 │
│ │ POST /upload     │     │ 4. wait_spark      │                 │
│ │ - Store file     │     │ 5. publish_success │                 │
│ │ - Send to Kafka  │     └────────┬────────────┘                 │
│ └──────────────────┘              │                               │
│                                   ▼                               │
│                        ┌──────────────────┐                       │
│                        │   Apache NiFi    │                       │
│                        │ (Data Ingest)    │                       │
│                        │                  │                       │
│                        │ Processors:      │                       │
│                        │ • ConsumeKafka   │                       │
│                        │ • ValidateRecord │                       │
│                        │ • TransformJSON  │                       │
│                        │ • PutS3Object    │                       │
│                        └────────┬─────────┘                       │
│                                 │                                │
│                                 ▼                                │
│                      ┌──────────────────┐                        │
│                      │  MinIO (S3 API)  │                        │
│                      │                  │                        │
│                      │ Buckets:         │                        │
│                      │ • raw/           │                        │
│                      │ • warehouse/     │                        │
│                      └──────────────────┘                        │
│                                                                  │
└────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    TRANSFORMATION LAYER                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Airflow Task 3: Submit Spark Job                                 │
│  ┌────────────────────────────────────────────────┐               │
│  │ kubectl apply -f spark-bronze-job.yaml         │               │
│  │ (No Git, Direct to K8s)                         │               │
│  └────────────────────────────────────────────────┘               │
│                         │                                          │
│                         ▼                                          │
│  ┌────────────────────────────────────────────────┐               │
│  │    Spark Application (Spark Operator)          │               │
│  │                                                │               │
│  │  Job: bronze_transform.py                      │               │
│  │  Input: s3a://raw/*.parquet                    │               │
│  │  Output: Iceberg tables (bronze warehouse)     │               │
│  │                                                │               │
│  │  Tasks:                                        │               │
│  │  1. Read from MinIO raw bucket                 │               │
│  │  2. Validate data quality                      │               │
│  │  3. Transform to standard schema               │               │
│  │  4. Write to Iceberg Bronze warehouse          │               │
│  │  5. Register table in Lakekeeper               │               │
│  └────────────────────────────────────────────────┘               │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐              │
│  │  MinIO (S3 API)      │  │  Lakekeeper          │              │
│  │                      │  │  (Iceberg Catalog)   │              │
│  │ Buckets:             │  │                      │              │
│  │ • raw/               │  │ Warehouses:          │              │
│  │   └─ orders.parquet  │  │ • bronze_warehouse   │              │
│  │   └─ customers.par   │  │   └─ orders (table)  │              │
│  │                      │  │   └─ customers       │              │
│  │ • warehouse/         │  │ • silver_warehouse   │              │
│  │   └─ bronze/         │  │ • gold_warehouse     │              │
│  │   └─ silver/         │  │                      │              │
│  │   └─ gold/           │  │ Features:            │              │
│  │                      │  │ • Time travel        │              │
│  │ Features:            │  │ • Schema evolution   │              │
│  │ • S3-compatible      │  │ • ACID transactions  │              │
│  │ • Multi-tenancy      │  │ • Data versioning    │              │
│  │ • ACL/Policy         │  │                      │              │
│  └──────────────────────┘  └──────────────────────┘              │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                │
│  │     PostgreSQL (Metadata Storage)            │                │
│  │                                              │                │
│  │  Databases:                                  │                │
│  │  • airflow_db (Airflow metadata)             │                │
│  │  • data_catalog (Custom metadata)            │                │
│  │    └─ tables, lineage, metrics               │                │
│  │                                              │                │
│  │  Tables:                                     │                │
│  │  • dag_runs, task_instances                  │                │
│  │  • table_lineage, data_quality               │                │
│  └──────────────────────────────────────────────┘                │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Roles

| Component | Role | Responsibility |
|-----------|------|-----------------|
| **Datasource API** | Entry Point | Accept file uploads, publish to Kafka |
| **Kafka** | Message Bus | Orchestrate workflow via events |
| **Airflow** | Orchestrator | Listen to events, trigger workflows, submit jobs |
| **NiFi** | Data Ingestion | Read from sources, validate, transform, load to MinIO |
| **MinIO** | Data Lake | Store raw data & Iceberg warehouse |
| **Spark** | Transformation | Transform raw → bronze (Iceberg) |
| **Lakekeeper** | Catalog | Manage Iceberg table metadata |
| **PostgreSQL** | Metadata Store | Airflow metadata + custom lineage |

---

## 2. Detailed Flow

### 2.1 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: FILE UPLOAD & KAFKA PUBLISH                            │
└─────────────────────────────────────────────────────────────────┘

User / API Client
    │
    └─ POST /api/upload
       ├─ file: orders_001.csv
       └─ format: CSV
            │
            ▼
    Datasource API (FastAPI)
    ├─ Receive file
    ├─ Store to temp location
    ├─ Create metadata:
    │  ├─ filename: orders_001.csv
    │  ├─ size: 1.2 MB
    │  ├─ content_type: text/csv
    │  ├─ timestamp: 2025-01-15T14:30:00Z
    │  └─ upload_id: upload-20250115-001
    │
    ├─ Publish to Kafka topic: file-uploaded
    │  Message:
    │  {
    │    "filename": "orders_001.csv",
    │    "upload_path": "s3a://uploads/orders_001.csv",
    │    "size": 1248576,
    │    "content_type": "text/csv",
    │    "timestamp": "2025-01-15T14:30:00Z",
    │    "upload_id": "upload-20250115-001"
    │  }
    │
    └─ Return HTTP 202 Accepted

┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: AIRFLOW LISTENS TO KAFKA & TRIGGERS WORKFLOW           │
└─────────────────────────────────────────────────────────────────┘

Airflow Sensor (Runs continuously)
    │
    ├─ Listen to Kafka topic: file-uploaded
    ├─ Detect new message from Datasource API
    │
    └─ TRIGGER: data_ingestion DAG
       ├─ Passed parameters:
       │  ├─ filename: orders_001.csv
       │  ├─ upload_path: s3a://uploads/orders_001.csv
       │  └─ upload_id: upload-20250115-001
       │
       └─ DAG RUN ID: data-ingestion-20250115-143000-001

┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: AIRFLOW DAG TASK 1 - TRIGGER NIFI INGEST              │
└─────────────────────────────────────────────────────────────────┘

Airflow DAG: data_ingestion (run_id: 20250115-143000-001)
    │
    └─ Task 1: trigger_nifi_flow
       ├─ Extract parameters:
       │  └─ filename: orders_001.csv
       │
       ├─ Call NiFi REST API:
       │  POST http://nifi:8080/nifi-api/process-groups/xyz/start
       │  Body:
       │  {
       │    "processorGroupId": "data-ingestion-pg",
       │    "variables": {
       │      "input_file": "s3a://uploads/orders_001.csv",
       │      "output_bucket": "s3a://raw/",
       │      "data_type": "orders"
       │    }
       │  }
       │
       ├─ NiFi Response: 200 OK
       │  └─ flow_run_id: nifi-flow-20250115-001
       │
       ├─ Save to XCom:
       │  └─ nifi_flow_run_id: nifi-flow-20250115-001
       │
       └─ Task Status: SUCCESS ✅

┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: NIFI INGESTS DATA (PARALLEL EXECUTION)                 │
└─────────────────────────────────────────────────────────────────┘

NiFi Process Group: DataIngestionFlow
    │
    ├─ Processor 1: ConsumeKafka
    │  └─ Read from Kafka topic: file-uploaded
    │     ├─ Consume message from Step 1
    │     └─ Extract: upload_path, filename, timestamp
    │
    ├─ Processor 2: FetchS3Object
    │  └─ Fetch file from upload location
    │     ├─ Read: s3a://uploads/orders_001.csv
    │     ├─ Parse as CSV
    │     └─ Preview: 1000 rows
    │
    ├─ Processor 3: ValidateRecord
    │  ├─ Schema validation
    │  │  ├─ Required columns: order_id, customer_id, amount, date
    │  │  ├─ Data types: int, int, decimal, date
    │  │  └─ Not null checks
    │  │
    │  └─ Route:
    │     ├─ Valid records → Next processor (95%)
    │     └─ Invalid records → Error bucket (5%)
    │
    ├─ Processor 4: UpdateAttribute
    │  ├─ Add processing metadata:
    │  │  ├─ ingest_timestamp: 2025-01-15T14:30:05Z
    │  │  ├─ processing_date: 2025-01-15
    │  │  ├─ data_version: v1
    │  │  ├─ source_system: datasource-api
    │  │  └─ record_count: 1000
    │  │
    │  └─ Set filename for output
    │
    ├─ Processor 5: ConvertRecord
    │  ├─ Input format: CSV
    │  ├─ Output format: Parquet
    │  │  (Better compression, nested schema support for Iceberg)
    │  │
    │  └─ Schema mapping:
    │     ├─ order_id → order_id (BIGINT)
    │     ├─ customer_id → customer_id (BIGINT)
    │     ├─ amount → amount (DECIMAL(10,2))
    │     ├─ date → order_date (DATE)
    │     └─ metadata → _metadata (STRUCT)
    │
    ├─ Processor 6: PutS3Object
    │  ├─ Write to MinIO
    │  ├─ S3 URI: s3a://raw/orders/2025-01-15/orders_001.parquet
    │  │  (Partitioned by date for faster queries)
    │  │
    │  ├─ Success: Write to Kafka topic: raw-data-ready
    │  │  Message:
    │  │  {
    │  │    "file_path": "s3a://raw/orders/2025-01-15/orders_001.parquet",
    │  │    "data_type": "orders",
    │  │    "record_count": 1000,
    │  │    "processing_date": "2025-01-15",
    │  │    "ingest_completed_at": "2025-01-15T14:30:15Z",
    │  │    "upload_id": "upload-20250115-001"
    │  │  }
    │  │
    │  └─ Failure: Route to error handling
    │
    └─ Duration: ~10 seconds

┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: AIRFLOW TASK 2 - WAIT FOR NIFI COMPLETION             │
└─────────────────────────────────────────────────────────────────┘

Airflow Task 2: wait_nifi_completion
    │
    ├─ Method 1: Monitor Kafka topic: raw-data-ready
    │  ├─ Wait for message matching upload_id
    │  ├─ Timeout: 5 minutes
    │  ├─ Extract from message:
    │  │  ├─ file_path: s3a://raw/orders/2025-01-15/orders_001.parquet
    │  │  ├─ record_count: 1000
    │  │  └─ processing_date: 2025-01-15
    │  │
    │  └─ Save to XCom:
    │     ├─ raw_file_path: s3a://raw/orders/2025-01-15/orders_001.parquet
    │     └─ record_count: 1000
    │
    └─ Task Status: SUCCESS ✅

┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: AIRFLOW TASK 3 - SUBMIT SPARK JOB                      │
└─────────────────────────────────────────────────────────────────┘

Airflow Task 3: submit_spark_job
    │
    ├─ Load Spark job template:
    │  └─ Template: spark-bronze-transform.yaml
    │
    ├─ Render template with parameters:
    │  ├─ job_id: bronze-dag-20250115-143000-001
    │  ├─ input_path: s3a://raw/orders/2025-01-15/orders_001.parquet
    │  ├─ output_warehouse: bronze_warehouse
    │  ├─ table_name: orders
    │  ├─ processing_date: 2025-01-15
    │  ├─ lakekeeper_uri: http://lakekeeper:8080
    │  ├─ minio_endpoint: http://minio:9000
    │  ├─ driver_cores: 2
    │  ├─ driver_memory: 2Gi
    │  ├─ executor_cores: 2
    │  ├─ executor_instances: 3
    │  └─ executor_memory: 4Gi
    │
    ├─ Write manifest to temp file:
    │  └─ /tmp/spark-bronze-job-20250115-143000-001.yaml
    │
    ├─ Submit to Kubernetes:
    │  └─ kubectl apply -f /tmp/spark-bronze-job-20250115-143000-001.yaml
    │     -n data-platform
    │
    ├─ Verify submission:
    │  ├─ Check if SparkApplication was created
    │  ├─ Get job_id from status
    │  └─ Save to XCom:
    │     └─ spark_job_id: bronze-dag-20250115-143000-001
    │
    └─ Task Status: SUCCESS ✅ (submission, not completion)

┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: SPARK JOB EXECUTES (TRANSFORMATION)                    │
└─────────────────────────────────────────────────────────────────┘

Kubernetes Spark Operator
    │
    └─ Create SparkApplication: bronze-dag-20250115-143000-001
       ├─ Driver Pod (1 pod):
       │  ├─ Cores: 2
       │  ├─ Memory: 2Gi
       │  └─ Status: Running
       │
       └─ Executor Pods (3 pods):
          ├─ Pod 1: executor-1
          │  ├─ Cores: 2 each = 6 total cores
          │  ├─ Memory: 4Gi each = 12Gi total memory
          │  └─ Status: Running
          │
          ├─ Pod 2: executor-2
          └─ Pod 3: executor-3
             └─ Status: All Running ✅

Spark Application: bronze_transform.py
    │
    ├─ STEP 7.1: Read from MinIO
    │  │
    │  ├─ Connect to MinIO (S3-compatible)
    │  │  ├─ Endpoint: http://minio:9000
    │  │  ├─ Access Key: XXXX
    │  │  └─ Secret Key: XXXX
    │  │
    │  ├─ Read parquet file:
    │  │  └─ s3a://raw/orders/2025-01-15/orders_001.parquet
    │  │
    │  └─ Load into DataFrame (DataFrame API)
    │     └─ Schema: order_id, customer_id, amount, order_date, _metadata
    │
    ├─ STEP 7.2: Data Validation & Quality Checks
    │  │
    │  ├─ Row count validation:
    │  │  ├─ Count: 1000 rows
    │  │  └─ Status: PASS ✅
    │  │
    │  ├─ Null value checks:
    │  │  ├─ order_id: 0 nulls ✅
    │  │  ├─ customer_id: 0 nulls ✅
    │  │  ├─ amount: 0 nulls ✅
    │  │  └─ order_date: 0 nulls ✅
    │  │
    │  ├─ Data type validation:
    │  │  ├─ order_id: BIGINT ✅
    │  │  ├─ customer_id: BIGINT ✅
    │  │  ├─ amount: DECIMAL(10,2) ✅
    │  │  └─ order_date: DATE ✅
    │  │
    │  ├─ Business logic validation:
    │  │  ├─ amount > 0: 998 rows ✅
    │  │  ├─ amount < 1000000: 1000 rows ✅
    │  │  ├─ order_date >= 2025-01-01: 1000 rows ✅
    │  │  └─ Reject 2 invalid rows → Error table
    │  │
    │  └─ Log metrics to PostgreSQL
    │
    ├─ STEP 7.3: Transform to Standard Schema
    │  │
    │  ├─ Column transformations:
    │  │  ├─ order_id: No change
    │  │  ├─ customer_id: No change
    │  │  ├─ amount: Round to 2 decimals
    │  │  ├─ order_date: Convert to DATE type
    │  │  ├─ processing_date: 2025-01-15
    │  │  ├─ ingest_timestamp: Extract from _metadata.ingest_timestamp
    │  │  ├─ data_version: Set to "v1"
    │  │  └─ source_system: Set to "datasource-api"
    │  │
    │  ├─ Add computed columns:
    │  │  ├─ year: Extract from order_date → 2025
    │  │  ├─ month: Extract from order_date → 01
    │  │  ├─ day: Extract from order_date → 15
    │  │  └─ updated_at: Current timestamp
    │  │
    │  └─ Final schema:
    │     ├─ order_id (BIGINT)
    │     ├─ customer_id (BIGINT)
    │     ├─ amount (DECIMAL(10,2))
    │     ├─ order_date (DATE)
    │     ├─ processing_date (DATE)
    │     ├─ ingest_timestamp (TIMESTAMP)
    │     ├─ data_version (STRING)
    │     ├─ source_system (STRING)
    │     ├─ year (INT)
    │     ├─ month (INT)
    │     ├─ day (INT)
    │     └─ updated_at (TIMESTAMP)
    │
    ├─ STEP 7.4: Register Iceberg Catalog (Lakekeeper)
    │  │
    │  ├─ Initialize Iceberg Catalog:
    │  │  ├─ Type: REST Catalog (Lakekeeper)
    │  │  ├─ URI: http://lakekeeper:8080
    │  │  └─ Warehouse: s3a://warehouse/bronze/
    │  │
    │  └─ Code:
    │     spark.sql.catalog.iceberg = \
    │     org.apache.iceberg.spark.SparkCatalog
    │     spark.sql.catalog.iceberg.type = rest
    │     spark.sql.catalog.iceberg.uri = \
    │     http://lakekeeper:8080
    │     spark.sql.catalog.iceberg.warehouse = \
    │     s3a://warehouse/bronze/
    │
    ├─ STEP 7.5: Write to Iceberg Table (Bronze Layer)
    │  │
    │  ├─ Table namespace: bronze_warehouse
    │  ├─ Table name: orders
    │  ├─ Full path: bronze_warehouse.orders
    │  │
    │  ├─ Create or merge to Iceberg table:
    │  │  df_bronze.writeTo("iceberg.bronze_warehouse.orders")
    │  │     .tableProperty("write.merge.mode", "copy-on-write")
    │  │     .tableProperty("format-version", "2")
    │  │     .mode("append")
    │  │     .partitionedBy("year", "month", "day")
    │  │     .option("write.parquet.compression-codec", "snappy")
    │  │     .option("iceberg.parquet.use-spark-writeSchema", "true")
    │  │     .saveAsTable()
    │  │
    │  ├─ Write result:
    │  │  ├─ Rows written: 998
    │  │  ├─ Rows rejected: 2
    │  │  ├─ Duration: 25 seconds
    │  │  └─ Output path: s3a://warehouse/bronze/orders/year=2025/month=01/day=15/
    │  │
    │  └─ Iceberg metadata updated:
    │     ├─ Current snapshot ID: 4567890
    │     ├─ Manifest files: v1, v2, v3
    │     ├─ Partition data files: 3 files
    │     └─ Schema evolution: OK (backward compatible)
    │
    ├─ STEP 7.6: Register Table in Lakekeeper
    │  │
    │  ├─ Call Lakekeeper REST API:
    │  │  POST http://lakekeeper:8080/catalogs/bronze_warehouse/namespaces/default/tables
    │  │
    │  ├─ Metadata:
    │  │  ├─ Table name: orders
    │  │  ├─ Location: s3a://warehouse/bronze/orders/
    │  │  ├─ Format: ICEBERG
    │  │  ├─ Partition columns: year, month, day
    │  │  ├─ Columns: (as defined above)
    │  │  ├─ Created at: 2025-01-15T14:30:50Z
    │  │  ├─ Modified at: 2025-01-15T14:30:50Z
    │  │  └─ Table properties:
    │  │     ├─ source_system: datasource-api
    │  │     ├─ data_version: v1
    │  │     ├─ sla: 24h
    │  │     └─ owner: data-platform-team
    │  │
    │  ├─ Lakekeeper response: 201 Created
    │  │  ├─ Warehouse ID: bronze_warehouse_123
    │  │  └─ Table ID: orders_456
    │  │
    │  └─ Metadata stored in Lakekeeper
    │
    ├─ STEP 7.7: Log Job Metrics
    │  │
    │  ├─ Write to PostgreSQL: job_metrics table
    │  │  ├─ job_id: bronze-dag-20250115-143000-001
    │  │  ├─ job_name: bronze_transform
    │  │  ├─ status: SUCCESS
    │  │  ├─ input_records: 1000
    │  │  ├─ output_records: 998
    │  │  ├─ rejected_records: 2
    │  │  ├─ duration_seconds: 45
    │  │  ├─ start_time: 2025-01-15T14:30:20Z
    │  │  ├─ end_time: 2025-01-15T14:31:05Z
    │  │  ├─ spark_application_id: application_1705325400000_0001
    │  │  ├─ table_name: bronze_warehouse.orders
    │  │  ├─ output_path: s3a://warehouse/bronze/orders/year=2025/month=01/day=15/
    │  │  └─ created_at: 2025-01-15T14:31:05Z
    │  │
    │  └─ Write to PostgreSQL: data_quality_metrics table
    │     ├─ job_id: bronze-dag-20250115-143000-001
    │     ├─ check_name: null_check_order_id
    │     ├─ check_status: PASS
    │     ├─ check_value: 0 nulls
    │     └─ created_at: 2025-01-15T14:31:05Z
    │
    └─ STEP 7.8: Spark Job Completes
       │
       ├─ Status: SUCCESS ✅
       ├─ Exit code: 0
       ├─ Total duration: 45 seconds
       └─ Driver logs available in kubectl

┌─────────────────────────────────────────────────────────────────┐
│ STEP 8: AIRFLOW TASK 4 - MONITOR SPARK JOB COMPLETION         │
└─────────────────────────────────────────────────────────────────┘

Airflow Task 4: wait_spark_completion
    │
    ├─ Monitor SparkApplication status via Kubernetes:
    │  ├─ kubectl get sparkapplication bronze-dag-20250115-143000-001
    │  ├─ Poll every 10 seconds
    │  └─ Timeout: 30 minutes
    │
    ├─ Check status conditions:
    │  ├─ Phase: SUCCEEDED ✅
    │  ├─ Conditions:
    │  │  ├─ Type: Submitted ✅
    │  │  ├─ Type: Running ✅
    │  │  ├─ Type: Succeeded ✅
    │  │  └─ Message: Application completed successfully
    │  │
    │  └─ Driver pod logs:
    │     ├─ Timestamp 14:30:50: Spark context started
    │     ├─ Timestamp 14:31:00: Reading from S3
    │     ├─ Timestamp 14:31:15: Data validation completed
    │     ├─ Timestamp 14:31:30: Writing to Iceberg
    │     └─ Timestamp 14:31:05: Job completed successfully
    │
    ├─ Extract job metrics:
    │  ├─ Query PostgreSQL job_metrics table:
    │  │  └─ WHERE job_id = 'bronze-dag-20250115-143000-001'
    │  │
    │  └─ Retrieve:
    │     ├─ output_records: 998
    │     ├─ rejected_records: 2
    │     ├─ duration_seconds: 45
    │     └─ table_name: bronze_warehouse.orders
    │
    ├─ Verify success criteria:
    │  ├─ Spark job status: SUCCESS ✅
    │  ├─ Output records > 0: 998 > 0 ✅
    │  ├─ Iceberg table exists: ✅
    │  └─ Lakekeeper registration: ✅
    │
    └─ Task Status: SUCCESS ✅

┌─────────────────────────────────────────────────────────────────┐
│ STEP 9: AIRFLOW TASK 5 - PUBLISH SUCCESS & CLEANUP            │
└─────────────────────────────────────────────────────────────────┘

Airflow Task 5: publish_success_metrics
    │
    ├─ Publish success message to Kafka:
    │  └─ Topic: bronze-layer-complete
    │     Message:
    │     {
    │       "upload_id": "upload-20250115-001",
    │       "workflow_id": "data-ingestion-20250115-143000-001",
    │       "status": "SUCCESS",
    │       "table_name": "bronze_warehouse.orders",
    │       "output_records": 998,
    │       "rejected_records": 2,
    │       "processing_date": "2025-01-15",
    │       "total_duration_seconds": 75,
    │       "completed_at": "2025-01-15T14:31:15Z"
    │     }
    │
    ├─ Clean up temporary files:
    │  ├─ Delete: /tmp/spark-bronze-job-*.yaml
    │  └─ Status: Cleaned
    │
    ├─ Log overall metrics:
    │  └─ PostgreSQL: workflow_execution table
    │     ├─ workflow_id: data-ingestion-20250115-143000-001
    │     ├─ status: SUCCESS
    │     ├─ start_time: 2025-01-15T14:30:00Z
    │     ├─ end_time: 2025-01-15T14:31:15Z
    │     ├─ total_duration_seconds: 75
    │     ├─ tasks_completed: 5
    │     ├─ tasks_failed: 0
    │     └─ created_at: 2025-01-15T14:31:15Z
    │
    └─ Task Status: SUCCESS ✅

┌─────────────────────────────────────────────────────────────────┐
│ COMPLETE WORKFLOW SUMMARY                                        │
└─────────────────────────────────────────────────────────────────┘

Timeline:
  14:30:00 - File uploaded to Datasource API
  14:30:01 - Message published to Kafka (file-uploaded)
  14:30:02 - Airflow Sensor detects event
  14:30:03 - Airflow DAG triggered
  14:30:05 - Task 1: trigger_nifi_flow (2 seconds)
  14:30:07 - NiFi ingest starts
  14:30:20 - Raw file written to MinIO
  14:30:21 - Message published to Kafka (raw-data-ready)
  14:30:22 - Task 2: wait_nifi_completion (15 seconds)
  14:30:23 - Task 3: submit_spark_job (1 second)
  14:30:24 - Spark job submitted to K8s
  14:30:25 - Spark driver & executors starting
  14:30:35 - Spark job executing transformation
  14:31:05 - Spark job completed
  14:31:10 - Task 4: wait_spark_completion (35 seconds)
  14:31:15 - Task 5: publish_success_metrics (5 seconds)
  14:31:15 - WORKFLOW COMPLETE ✅

Total Duration: 1 minute 15 seconds

Data Journey:
  User's CSV → Datasource API → MinIO (uploads/) →
  NiFi Ingestion → MinIO (raw/) → Spark Transformation →
  Iceberg Bronze Warehouse → Lakekeeper Metadata Catalog

Success Metrics:
  ✅ Input records: 1000
  ✅ Output records: 998
  ✅ Rejected records: 2
  ✅ Iceberg table: bronze_warehouse.orders
  ✅ Partitions: year=2025, month=01, day=15
  ✅ Data version: v1
  ✅ Source system: datasource-api
```

---

## 3. Implementation Details

### 3.1 Project Folder Structure

```
data-lakehouse/
│
├── README.md
├── .gitignore
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── FLOW.md
│   └── TROUBLESHOOTING.md
│
├── infra/
│   ├── k8s/
│   │   ├── namespace.yaml
│   │   ├── storage-class.yaml
│   │   │
│   │   ├── kafka/
│   │   │   ├── helm-values.yaml
│   │   │   ├── kafka-deployment.yaml
│   │   │   ├── kafka-topics.yaml
│   │   │   └── scripts/
│   │   │       ├── install_kafka.sh
│   │   │       └── create_topics.sh
│   │   │
│   │   ├── nifi/
│   │   │   ├── helm-values.yaml
│   │   │   ├── nifi-deployment.yaml
│   │   │   ├── processor-groups.json
│   │   │   └── scripts/
│   │   │       ├── install_nifi.sh
│   │   │       └── configure_nifi.sh
│   │   │
│   │   ├── spark-operator/
│   │   │   ├── helm-values.yaml
│   │   │   ├── spark-operator-deployment.yaml
│   │   │   ├── spark-rbac.yaml
│   │   │   └── scripts/
│   │   │       └── install_spark_operator.sh
│   │   │
│   │   ├── airflow/
│   │   │   ├── helm-values.yaml
│   │   │   ├── airflow-deployment.yaml
│   │   │   ├── airflow-rbac.yaml
│   │   │   ├── airflow-configs.yaml
│   │   │   └── scripts/
│   │   │       ├── install_airflow.sh
│   │   │       └── configure_airflow.sh
│   │   │
│   │   ├── minio/
│   │   │   ├── helm-values.yaml
│   │   │   ├── minio-deployment.yaml
│   │   │   ├── minio-init-bucket.yaml
│   │   │   └── scripts/
│   │   │       ├── install_minio.sh
│   │   │       └── create_buckets.sh
│   │   │
│   │   ├── postgresql/
│   │   │   ├── helm-values.yaml
│   │   │   ├── postgresql-deployment.yaml
│   │   │   ├── database-init.sql
│   │   │   └── scripts/
│   │   │       └── install_postgresql.sh
│   │   │
│   │   └── lakekeeper/
│   │       ├── helm-values.yaml
│   │       ├── lakekeeper-deployment.yaml
│   │       └── scripts/
│   │           └── install_lakekeeper.sh
│   │
│   ├── docker-compose/
│   │   ├── docker-compose.yaml (Local dev)
│   │   └── .env.example
│   │
│   └── scripts/
│       ├── setup_k8s_cluster.sh
│       ├── setup_namespaces.sh
│       ├── setup_secrets.sh
│       ├── install_all_components.sh
│       └── cleanup_all.sh
│
├── airflow-dags/
│   ├── README.md
│   ├── requirements.txt
│   ├── dags/
│   │   ├── __init__.py
│   │   ├── data_ingestion.py          # MAIN DAG
│   │   └── monitoring_dag.py
│   │
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── sensors/
│   │   │   ├── __init__.py
│   │   │   └── kafka_sensor.py         # Custom Kafka sensor
│   │   │
│   │   ├── operators/
│   │   │   ├── __init__.py
│   │   │   ├── nifi_operator.py        # Trigger NiFi flow
│   │   │   └── spark_operator.py       # Submit Spark job
│   │   │
│   │   └── hooks/
│   │       ├── __init__.py
│   │       ├── nifi_hook.py            # NiFi API connection
│   │       ├── kafka_hook.py           # Kafka connection
│   │       └── k8s_hook.py             # Kubernetes connection
│   │
│   ├── config/
│   │   ├── airflow.cfg
│   │   └── logging.conf
│   │
│   └── docker/
│       ├── Dockerfile
│       └── entrypoint.sh
│
├── spark-jobs/
│   ├── README.md
│   ├── requirements.txt
│   │
│   ├── bronze-layer/
│   │   ├── bronze_transform.py         # Main Spark job
│   │   ├── config.yaml
│   │   ├── Dockerfile
│   │   └── tests/
│   │       ├── test_bronze_transform.py
│   │       └── test_data.py
│   │
│   ├── spark-configs/
│   │   ├── spark-defaults.conf
│   │   └── log4j.properties
│   │
│   └── utils/
│       ├── __init__.py
│       ├── iceberg_utils.py            # Iceberg operations
│       ├── data_quality.py             # DQ checks
│       ├── s3_utils.py                 # MinIO operations
│       ├── logger.py
│       └── config.py
│
├── datasource-api/
│   ├── README.md
│   ├── main.py
│   ├── requirements.txt
│   ├── config.py
│   ├── Dockerfile
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── upload.py                  # File upload endpoint
│   │   ├── health.py                  # Health check
│   │   └── metadata.py                # Metadata retrieval
│   │
│   └── schemas/
│       ├── __init__.py
│       └── upload.py                  # Pydantic schemas
│
├── kubernetes-manifests/
│   ├── spark-job-templates/
│   │   ├── bronze-transform.yaml       # SparkApplication template
│   │   ├── silver-transform.yaml
│   │   └── gold-transform.yaml
│   │
│   ├── configmaps/
│   │   ├── spark-config.yaml
│   │   └── airflow-config.yaml
│   │
│   └── secrets/
│       ├── minio-credentials.yaml
│       └── database-credentials.yaml
│
└── monitoring/
    ├── prometheus/
    │   ├── prometheus-config.yaml
    │   └── prometheus-deployment.yaml
    │
    └── grafana/
        ├── grafana-deployment.yaml
        └── dashboards/
            ├── airflow-dashboard.json
            ├── spark-dashboard.json
            └── pipeline-dashboard.json
```

### 3.2 Airflow DAG Implementation

```python
# airflow-dags/dags/data_ingestion.py

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.apache.kafka.sensors.kafka import KafkaConsumerSensor
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from airflow.utils.decorators import apply_defaults
import json
import subprocess
import time
from plugins.operators.nifi_operator import NiFiOperator
from plugins.operators.spark_operator import SparkOperator
import logging

logger = logging.getLogger(__name__)

# DAG Configuration
default_args = {
    'owner': 'data-platform-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': True,
    'email': ['data-team@company.com']
}

dag = DAG(
    'data_ingestion',
    default_args=default_args,
    description='Ingest raw data → transform to Bronze Iceberg layer',
    schedule_interval=None,  # Trigger manually or from Kafka
    catchup=False,
    tags=['data-ingestion', 'bronze-layer']
)

# ============================================================================
# TASK 1: Listen to Kafka & Trigger DAG
# ============================================================================

# This sensor runs on a schedule and listens to Kafka topic
# When a message arrives, it triggers this DAG run
kafka_sensor = KafkaConsumerSensor(
    task_id='listen_kafka_file_uploaded',
    topics=['file-uploaded'],
    bootstrap_servers=['kafka:9092'],
    group_id='airflow-data-ingestion',
    api_version=(0, 10, 1),
    consumer_timeout_ms=5000,
    mode='once',
    poke_interval=10,
    timeout=600,
    dag=dag,
)

# ============================================================================
# TASK 2: Trigger NiFi Data Ingestion Flow
# ============================================================================

def trigger_nifi_flow(**context):
    """
    Trigger NiFi to ingest raw file to MinIO
    
    Input: Kafka message from task 1
    Output: raw file in MinIO (s3a://raw/)
    """
    
    # Get Kafka message from sensor
    kafka_message = context['task_instance'].xcom_pull(
        task_ids='listen_kafka_file_uploaded'
    )
    
    logger.info(f"Received Kafka message: {kafka_message}")
    
    # Parse message
    message_data = json.loads(kafka_message)
    filename = message_data['filename']
    upload_path = message_data['upload_path']
    upload_id = message_data['upload_id']
    
    logger.info(f"Triggering NiFi for file: {filename}")
    
    # Call NiFi REST API to start process group
    nifi_api_url = "http://nifi:8080/nifi-api"
    process_group_id = "data-ingestion-pg-xyz"  # Get from NiFi UI
    
    # Get process group details
    response = subprocess.run([
        'curl', '-s',
        f'{nifi_api_url}/process-groups/{process_group_id}'
    ], capture_output=True, text=True)
    
    pg_state = json.loads(response.stdout)
    
    # Start process group
    start_payload = {
        "id": process_group_id,
        "state": "RUNNING"
    }
    
    response = subprocess.run([
        'curl', '-X', 'PUT',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(start_payload),
        f'{nifi_api_url}/process-groups/{process_group_id}'
    ], capture_output=True, text=True)
    
    logger.info(f"NiFi response: {response.stdout}")
    
    # Save to XCom for next task
    context['task_instance'].xcom_push(
        key='nifi_flow_id',
        value=process_group_id
    )
    
    context['task_instance'].xcom_push(
        key='filename',
        value=filename
    )
    
    context['task_instance'].xcom_push(
        key='upload_id',
        value=upload_id
    )
    
    context['task_instance'].xcom_push(
        key='upload_path',
        value=upload_path
    )
    
    logger.info(f"✅ NiFi flow triggered successfully")

trigger_nifi = PythonOperator(
    task_id='trigger_nifi_flow',
    python_callable=trigger_nifi_flow,
    provide_context=True,
    dag=dag
)

# ============================================================================
# TASK 3: Wait for NiFi Completion (via Kafka)
# ============================================================================

def wait_nifi_completion(**context):
    """
    Wait for NiFi to complete ingestion
    Monitor Kafka topic: raw-data-ready
    """
    
    upload_id = context['task_instance'].xcom_pull(
        task_ids='trigger_nifi_flow',
        key='upload_id'
    )
    
    logger.info(f"Waiting for NiFi completion (upload_id: {upload_id})")
    
    # Listen to Kafka topic: raw-data-ready
    bootstrap_servers = ['kafka:9092']
    topic = 'raw-data-ready'
    group_id = f'airflow-nifi-monitor-{upload_id}'
    
    from confluent_kafka import Consumer, KafkaError
    
    config = {
        'bootstrap.servers': ','.join(bootstrap_servers),
        'group.id': group_id,
        'auto.offset.reset': 'latest',
        'enable.auto.commit': True,
    }
    
    consumer = Consumer(config)
    consumer.subscribe([topic])
    
    timeout_seconds = 300  # 5 minutes
    start_time = time.time()
    raw_file_path = None
    
    try:
        while True:
            msg = consumer.poll(timeout=1)
            
            if msg is None:
                # No message, check timeout
                if time.time() - start_time > timeout_seconds:
                    raise Exception(f"Timeout waiting for NiFi completion (upload_id: {upload_id})")
                continue
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    raise KafkaError(msg.error())
            
            # Parse message
            message_data = json.loads(msg.value().decode('utf-8'))
            
            # Check if this is our message
            if message_data.get('upload_id') == upload_id:
                logger.info(f"✅ NiFi completed: {message_data}")
                raw_file_path = message_data['file_path']
                record_count = message_data['record_count']
                
                # Save to XCom
                context['task_instance'].xcom_push(
                    key='raw_file_path',
                    value=raw_file_path
                )
                
                context['task_instance'].xcom_push(
                    key='record_count',
                    value=record_count
                )
                
                break
    
    finally:
        consumer.close()
    
    logger.info(f"Raw file ready: {raw_file_path}")

wait_nifi = PythonOperator(
    task_id='wait_nifi_completion',
    python_callable=wait_nifi_completion,
    provide_context=True,
    dag=dag,
    timeout=600  # 10 minutes
)

# ============================================================================
# TASK 4: Submit Spark Job (Raw → Bronze)
# ============================================================================

def submit_spark_job(**context):
    """
    Submit Spark job to K8s via kubectl apply
    Transform: raw → bronze (Iceberg)
    """
    
    # Get parameters from previous tasks
    filename = context['task_instance'].xcom_pull(
        task_ids='trigger_nifi_flow',
        key='filename'
    )
    
    upload_id = context['task_instance'].xcom_pull(
        task_ids='trigger_nifi_flow',
        key='upload_id'
    )
    
    raw_file_path = context['task_instance'].xcom_pull(
        task_ids='wait_nifi_completion',
        key='raw_file_path'
    )
    
    dag_run_id = context['dag_run'].run_id
    job_id = f"bronze-{dag_run_id}"
    
    logger.info(f"Submitting Spark job: {job_id}")
    logger.info(f"Input: {raw_file_path}")
    
    # Load SparkApplication template
    template_path = "/opt/airflow/kubernetes-manifests/spark-job-templates/bronze-transform.yaml"
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # Render template with parameters
    from jinja2 import Template
    
    template = Template(template_content)
    
    manifest = template.render(
        job_id=job_id,
        input_path=raw_file_path,
        output_warehouse="bronze_warehouse",
        table_name="orders",  # Can be derived from filename
        processing_date=datetime.now().strftime("%Y-%m-%d"),
        lakekeeper_uri="http://lakekeeper:8080",
        minio_endpoint="http://minio:9000",
        minio_access_key="{{ env.MINIO_ACCESS_KEY }}",
        minio_secret_key="{{ env.MINIO_SECRET_KEY }}",
        driver_cores=2,
        driver_memory="2Gi",
        executor_cores=2,
        executor_instances=3,
        executor_memory="4Gi"
    )
    
    # Write manifest to temp file
    manifest_file = f"/tmp/spark-{job_id}.yaml"
    with open(manifest_file, 'w') as f:
        f.write(manifest)
    
    logger.info(f"Manifest written to: {manifest_file}")
    
    # Submit to Kubernetes
    cmd = [
        'kubectl', 'apply',
        '-f', manifest_file,
        '-n', 'data-platform'
    ]
    
    logger.info(f"Executing: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"kubectl apply failed: {result.stderr}")
    
    logger.info(f"✅ SparkApplication created: {job_id}")
    logger.info(f"Response: {result.stdout}")
    
    # Save job_id to XCom for next task
    context['task_instance'].xcom_push(
        key='spark_job_id',
        value=job_id
    )
    
    # Clean up temp file
    import os
    os.remove(manifest_file)

submit_spark = PythonOperator(
    task_id='submit_spark_job',
    python_callable=submit_spark_job,
    provide_context=True,
    dag=dag
)

# ============================================================================
# TASK 5: Wait for Spark Job Completion
# ============================================================================

def wait_spark_completion(**context):
    """
    Monitor Spark job status via kubectl
    Poll SparkApplication resource until completion
    """
    
    job_id = context['task_instance'].xcom_pull(
        task_ids='submit_spark_job',
        key='spark_job_id'
    )
    
    logger.info(f"Waiting for Spark job: {job_id}")
    
    namespace = "data-platform"
    timeout_seconds = 1800  # 30 minutes
    start_time = time.time()
    poll_interval = 10
    
    while True:
        # Get SparkApplication status
        cmd = [
            'kubectl', 'get', 'sparkapplication', job_id,
            '-n', namespace,
            '-o', 'json'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"kubectl get failed: {result.stderr}")
        
        spark_app = json.loads(result.stdout)
        
        status = spark_app['status'].get('phase', 'UNKNOWN')
        conditions = spark_app['status'].get('conditions', [])
        
        logger.info(f"Spark job status: {status}")
        
        # Check completion
        if status == 'SUCCEEDED':
            logger.info(f"✅ Spark job SUCCEEDED: {job_id}")
            
            # Extract metrics
            driver_pod = spark_app['status'].get('driverInfo', {})
            
            context['task_instance'].xcom_push(
                key='spark_status',
                value='SUCCESS'
            )
            
            context['task_instance'].xcom_push(
                key='spark_job_id',
                value=job_id
            )
            
            break
        
        elif status == 'FAILED':
            logger.error(f"❌ Spark job FAILED: {job_id}")
            
            # Get logs
            driver_pod_name = spark_app['status'].get('driverInfo', {}).get('podName')
            if driver_pod_name:
                log_cmd = [
                    'kubectl', 'logs', driver_pod_name,
                    '-n', namespace
                ]
                log_result = subprocess.run(log_cmd, capture_output=True, text=True)
                logger.error(f"Driver logs:\n{log_result.stdout}")
            
            raise Exception(f"Spark job FAILED: {job_id}")
        
        elif status == 'RUNNING':
            logger.info(f"Spark job still running, will check again in {poll_interval}s")
        
        # Check timeout
        if time.time() - start_time > timeout_seconds:
            raise Exception(f"Timeout waiting for Spark job: {job_id}")
        
        # Wait before next poll
        time.sleep(poll_interval)

wait_spark = PythonOperator(
    task_id='wait_spark_completion',
    python_callable=wait_spark_completion,
    provide_context=True,
    dag=dag,
    timeout=2100  # 35 minutes (timeout_seconds + buffer)
)

# ============================================================================
# TASK 6: Publish Success & Cleanup
# ============================================================================

def publish_success(**context):
    """
    Publish success message to Kafka
    Log workflow metrics to PostgreSQL
    """
    
    upload_id = context['task_instance'].xcom_pull(
        task_ids='trigger_nifi_flow',
        key='upload_id'
    )
    
    filename = context['task_instance'].xcom_pull(
        task_ids='trigger_nifi_flow',
        key='filename'
    )
    
    dag_run_id = context['dag_run'].run_id
    job_id = f"bronze-{dag_run_id}"
    
    # Get metrics from PostgreSQL
    import psycopg2
    
    conn = psycopg2.connect(
        host="postgresql",
        database="airflow",
        user="airflow",
        password="airflow"
    )
    
    cur = conn.cursor()
    
    # Query job metrics
    cur.execute("""
        SELECT output_records, rejected_records, duration_seconds
        FROM public.job_metrics
        WHERE job_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (job_id,))
    
    row = cur.fetchone()
    
    if row:
        output_records, rejected_records, duration_seconds = row
    else:
        output_records = 0
        rejected_records = 0
        duration_seconds = 0
    
    cur.close()
    conn.close()
    
    # Publish to Kafka
    from confluent_kafka import Producer
    
    config = {
        'bootstrap.servers': 'kafka:9092',
    }
    
    producer = Producer(config)
    
    message = {
        "upload_id": upload_id,
        "filename": filename,
        "job_id": job_id,
        "status": "SUCCESS",
        "output_records": output_records,
        "rejected_records": rejected_records,
        "duration_seconds": duration_seconds,
        "completed_at": datetime.now().isoformat()
    }
    
    producer.produce(
        'bronze-layer-complete',
        json.dumps(message).encode('utf-8')
    )
    
    producer.flush()
    
    logger.info(f"✅ Success message published to Kafka")
    logger.info(f"Message: {message}")

publish_success_task = PythonOperator(
    task_id='publish_success',
    python_callable=publish_success,
    provide_context=True,
    dag=dag
)

# ============================================================================
# DAG Dependency Graph
# ============================================================================

kafka_sensor >> trigger_nifi >> wait_nifi >> submit_spark >> wait_spark >> publish_success_task
```

### 3.3 SparkApplication Manifest Template

```yaml
# kubernetes-manifests/spark-job-templates/bronze-transform.yaml

apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: {{ job_id }}
  namespace: data-platform
  labels:
    app: data-lakehouse
    layer: bronze
    job-id: {{ job_id }}
  annotations:
    description: "Transform raw → bronze (Iceberg)"

spec:
  type: Python
  pythonVersion: "3"
  mode: cluster
  image: spark:3.4.0-python3
  imagePullPolicy: IfNotPresent
  
  # Main application file (stored in MinIO)
  mainApplicationFile: "s3a://spark-jobs/bronze_transform.py"
  
  # Arguments to Spark job
  arguments:
    - "--input-path"
    - "{{ input_path }}"
    - "--output-warehouse"
    - "{{ output_warehouse }}"
    - "--table-name"
    - "{{ table_name }}"
    - "--processing-date"
    - "{{ processing_date }}"
    - "--lakekeeper-uri"
    - "{{ lakekeeper_uri }}"
    - "--minio-endpoint"
    - "{{ minio_endpoint }}"
    - "--minio-access-key"
    - "{{ minio_access_key }}"
    - "--minio-secret-key"
    - "{{ minio_secret_key }}"
  
  sparkVersion: "3.4.0"
  
  restartPolicy:
    type: Never
  
  # Driver configuration
  driver:
    cores: {{ driver_cores }}
    memory: {{ driver_memory }}
    memoryOverhead: 256m
    serviceAccount: spark
    volumeMounts:
      - name: spark-jars
        mountPath: /opt/spark/jars
  
  # Executor configuration
  executor:
    cores: {{ executor_cores }}
    instances: {{ executor_instances }}
    memory: {{ executor_memory }}
    memoryOverhead: 512m
    volumeMounts:
      - name: spark-jars
        mountPath: /opt/spark/jars
  
  # JVM configurations
  sparkConf:
    # Iceberg Catalog Configuration
    "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog"
    "spark.sql.catalog.iceberg.type": "rest"
    "spark.sql.catalog.iceberg.uri": "{{ lakekeeper_uri }}"
    "spark.sql.catalog.iceberg.warehouse": "s3a://warehouse/bronze/"
    "spark.sql.catalog.iceberg.s3.endpoint": "{{ minio_endpoint }}"
    "spark.sql.catalog.iceberg.s3.access-key-id": "{{ minio_access_key }}"
    "spark.sql.catalog.iceberg.s3.secret-access-key": "{{ minio_secret_key }}"
    
    # MinIO S3 Configuration
    "spark.hadoop.fs.s3a.endpoint": "{{ minio_endpoint }}"
    "spark.hadoop.fs.s3a.access.key": "{{ minio_access_key }}"
    "spark.hadoop.fs.s3a.secret.key": "{{ minio_secret_key }}"
    "spark.hadoop.fs.s3a.path.style.access": "true"
    "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem"
    
    # Performance tuning
    "spark.sql.shuffle.partitions": "200"
    "spark.sql.adaptive.enabled": "true"
    "spark.sql.adaptive.coalescePartitions.enabled": "true"
    "spark.sql.adaptive.skewJoin.enabled": "true"
    
    # Data source format
    "spark.sql.defaultCatalog": "iceberg"
    "spark.sql.parquet.compression.codec": "snappy"
    
    # Logging
    "spark.eventLog.enabled": "true"
    "spark.eventLog.dir": "s3a://logs/spark/"
  
  # Environment variables
  envVars:
    HADOOP_OPTIONAL_TOOLS: "hadoop-aws"
    AWS_S3_ENDPOINT: "{{ minio_endpoint }}"
    AWS_ACCESS_KEY_ID: "{{ minio_access_key }}"
    AWS_SECRET_ACCESS_KEY: "{{ minio_secret_key }}"
  
  # Volumes
  volumes:
    - name: spark-jars
      emptyDir: {}
  
  # Monitoring
  monitoring:
    exposeDriverMetrics: true
    exposeExecutorMetrics: true
    prometheus:
      jmxExporterConfig: |
        ---
        rules:
          - pattern: ".*"
```

### 3.4 Spark Job Implementation

```python
# spark-jobs/bronze-layer/bronze_transform.py

import argparse
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
from datetime import datetime
import json
import psycopg2

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments"""
    
    parser = argparse.ArgumentParser(description='Transform raw → bronze (Iceberg)')
    
    parser.add_argument('--input-path', required=True, help='Input path in MinIO')
    parser.add_argument('--output-warehouse', required=True, help='Iceberg warehouse name')
    parser.add_argument('--table-name', required=True, help='Target table name')
    parser.add_argument('--processing-date', required=True, help='Processing date (YYYY-MM-DD)')
    parser.add_argument('--lakekeeper-uri', required=True, help='Lakekeeper REST URI')
    parser.add_argument('--minio-endpoint', required=True, help='MinIO S3 endpoint')
    parser.add_argument('--minio-access-key', required=True, help='MinIO access key')
    parser.add_argument('--minio-secret-key', required=True, help='MinIO secret key')
    
    return parser.parse_args()

def init_spark_session(args):
    """Initialize Spark session with Iceberg & MinIO configuration"""
    
    spark = SparkSession.builder \
        .appName("bronze-transform") \
        .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.iceberg.type", "rest") \
        .config("spark.sql.catalog.iceberg.uri", args.lakekeeper_uri) \
        .config("spark.sql.catalog.iceberg.warehouse", "s3a://warehouse/bronze/") \
        .config("spark.hadoop.fs.s3a.endpoint", args.minio_endpoint) \
        .config("spark.hadoop.fs.s3a.access.key", args.minio_access_key) \
        .config("spark.hadoop.fs.s3a.secret.key", args.minio_secret_key) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.sql.parquet.compression.codec", "snappy") \
        .getOrCreate()
    
    logger.info("✅ Spark session initialized")
    return spark

def read_raw_data(spark, input_path):
    """Read raw Parquet file from MinIO"""
    
    logger.info(f"Reading raw data from: {input_path}")
    
    df = spark.read \
        .format("parquet") \
        .load(input_path)
    
    logger.info(f"✅ Loaded {df.count()} records")
    logger.info(f"Schema: {df.schema}")
    
    return df

def validate_data_quality(spark, df, job_id, table_name):
    """Validate data quality and log results"""
    
    logger.info("Starting data quality validation...")
    
    input_records = df.count()
    logger.info(f"Input records: {input_records}")
    
    # Row count validation
    if input_records == 0:
        raise Exception("Input data is empty!")
    
    # Null value checks
    null_checks = {}
    for column in df.columns:
        null_count = df.filter(col(column).isNull()).count()
        null_checks[column] = null_count
        logger.info(f"Null check - {column}: {null_count}")
    
    # Data type validation
    logger.info(f"Data types: {df.dtypes}")
    
    # Business logic validation
    # Example: filter orders with positive amount
    valid_df = df.filter(col("amount") > 0)
    valid_records = valid_df.count()
    rejected_records = input_records - valid_records
    
    logger.info(f"Valid records: {valid_records}")
    logger.info(f"Rejected records: {rejected_records}")
    
    # Log to PostgreSQL
    log_metrics_to_postgres(
        job_id=job_id,
        table_name=table_name,
        input_records=input_records,
        output_records=valid_records,
        rejected_records=rejected_records,
        checks=null_checks
    )
    
    return valid_df, valid_records, rejected_records

def transform_schema(df, processing_date):
    """Transform to standard Bronze schema"""
    
    logger.info("Transforming schema...")
    
    df_bronze = df \
        .withColumn("processing_date", lit(processing_date).cast(DateType())) \
        .withColumn("ingest_timestamp", current_timestamp()) \
        .withColumn("data_version", lit("v1")) \
        .withColumn("source_system", lit("datasource-api")) \
        .withColumn("year", year(col("order_date"))) \
        .withColumn("month", month(col("order_date"))) \
        .withColumn("day", dayofmonth(col("order_date"))) \
        .withColumn("updated_at", current_timestamp())
    
    # Select and order columns
    bronze_schema = [
        "order_id",
        "customer_id",
        "amount",
        "order_date",
        "processing_date",
        "ingest_timestamp",
        "data_version",
        "source_system",
        "year",
        "month",
        "day",
        "updated_at"
    ]
    
    df_bronze = df_bronze.select(bronze_schema)
    
    logger.info(f"✅ Schema transformed")
    logger.info(f"New schema: {df_bronze.schema}")
    
    return df_bronze

def write_to_iceberg(spark, df, output_warehouse, table_name):
    """Write DataFrame to Iceberg table"""
    
    logger.info(f"Writing to Iceberg table: {output_warehouse}.{table_name}")
    
    full_table_name = f"iceberg.{output_warehouse}.{table_name}"
    
    # Write to Iceberg
    df.writeTo(full_table_name) \
        .tableProperty("write.merge.mode", "copy-on-write") \
        .tableProperty("format-version", "2") \
        .tableProperty("commit.retry.num-retries", "3") \
        .mode("append") \
        .partitionedBy("year", "month", "day") \
        .option("write.parquet.compression-codec", "snappy") \
        .option("iceberg.parquet.use-spark-writeSchema", "true") \
        .saveAsTable()
    
    logger.info(f"✅ Data written to Iceberg")
    
    # Verify table
    df_check = spark.sql(f"SELECT COUNT(*) as count FROM {full_table_name}")
    row_count = df_check.collect()[0]['count']
    logger.info(f"✅ Iceberg table row count: {row_count}")
    
    return row_count

def log_metrics_to_postgres(**metrics):
    """Log job execution metrics to PostgreSQL"""
    
    try:
        conn = psycopg2.connect(
            host="postgresql",
            database="airflow",
            user="airflow",
            password="airflow"
        )
        
        cur = conn.cursor()
        
        # Insert job metrics
        cur.execute("""
            INSERT INTO public.job_metrics 
            (job_id, table_name, input_records, output_records, rejected_records, status, duration_seconds, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            metrics['job_id'],
            metrics['table_name'],
            metrics['input_records'],
            metrics['output_records'],
            metrics['rejected_records'],
            'SUCCESS',
            0,
            datetime.now()
        ))
        
        # Insert data quality checks
        for column, null_count in metrics['checks'].items():
            cur.execute("""
                INSERT INTO public.data_quality_metrics
                (job_id, check_name, check_status, check_value, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                metrics['job_id'],
                f"null_check_{column}",
                'PASS' if null_count == 0 else 'FAIL',
                str(null_count),
                datetime.now()
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info("✅ Metrics logged to PostgreSQL")
    
    except Exception as e:
        logger.error(f"Error logging metrics: {e}")

def main():
    """Main execution"""
    
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"BRONZE LAYER TRANSFORMATION")
    logger.info("=" * 80)
    logger.info(f"Input path: {args.input_path}")
    logger.info(f"Output warehouse: {args.output_warehouse}")
    logger.info(f"Table name: {args.table_name}")
    logger.info(f"Processing date: {args.processing_date}")
    
    try:
        # Initialize Spark
        spark = init_spark_session(args)
        
        # Read raw data
        df_raw = read_raw_data(spark, args.input_path)
        
        # Validate data quality
        job_id = spark.sparkContext.applicationId  # Get Spark app ID
        df_valid, output_records, rejected_records = validate_data_quality(
            spark, df_raw, job_id, args.table_name
        )
        
        # Transform schema
        df_bronze = transform_schema(df_valid, args.processing_date)
        
        # Write to Iceberg
        iceberg_row_count = write_to_iceberg(
            spark, df_bronze, args.output_warehouse, args.table_name
        )
        
        logger.info("=" * 80)
        logger.info(f"✅ BRONZE LAYER TRANSFORMATION COMPLETED SUCCESSFULLY")
        logger.info(f"Input records: {df_raw.count()}")
        logger.info(f"Output records: {output_records}")
        logger.info(f"Rejected records: {rejected_records}")
        logger.info(f"Iceberg table: {args.output_warehouse}.{args.table_name}")
        logger.info("=" * 80)
    
    except Exception as e:
        logger.error(f"❌ Error in bronze transformation: {e}", exc_info=True)
        raise
    
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
```

---

## 4. Tech Stack Summary

| Component | Technology | Purpose | Status |
|-----------|-----------|---------|--------|
| **Message Bus** | Apache Kafka | Orchestrate workflow via events | ✅ Included |
| **Orchestrator** | Apache Airflow | Trigger workflows, monitor jobs | ✅ Included |
| **Data Ingestion** | Apache NiFi | Read files, validate, transform, load to S3 | ✅ Included |
| **Data Lake** | MinIO (S3-compatible) | Store raw & Iceberg warehouse data | ✅ Included |
| **Transformation** | Apache Spark | Transform raw → bronze (Iceberg) | ✅ Included |
| **Table Format** | Apache Iceberg | ACID transactions, time travel, schema evolution | ✅ Included |
| **Catalog** | Lakekeeper (Iceberg REST) | Manage table metadata | ✅ Included |
| **Metadata Store** | PostgreSQL | Store Airflow metadata + custom lineage | ✅ Included |
| **GitOps** | ArgoCD | Manage K8s manifests | ❌ **Excluded** |
| **Compute Orchestration** | Spark Operator | Submit Spark jobs to K8s | ✅ Included |

---

## 5. Implementation Roadmap

### Phase 1: Infrastructure Setup (Week 1-2)

```bash
Step 1: Kubernetes cluster setup
  └─ kubectl, helm, storageclass

Step 2: Deploy storage layer
  ├─ PostgreSQL (metadata)
  ├─ MinIO (data lake)
  └─ Verify bucket creation

Step 3: Deploy message queue
  ├─ Kafka brokers
  ├─ Create topics (file-uploaded, raw-data-ready)
  └─ Test connectivity

Step 4: Deploy orchestration
  ├─ Spark Operator
  ├─ Airflow
  └─ Configure connections
```

### Phase 2: Data Ingestion (Week 2-3)

```bash
Step 1: Deploy NiFi
  ├─ Install via Helm
  ├─ Configure S3 credentials
  └─ Create processor groups

Step 2: Create Datasource API
  ├─ FastAPI server
  ├─ File upload endpoint
  ├─ Kafka producer
  └─ Deploy to K8s

Step 3: Test end-to-end ingestion
  ├─ Upload file via API
  ├─ Verify NiFi processing
  └─ Check raw bucket
```

### Phase 3: Spark Transformation (Week 3-4)

```bash
Step 1: Deploy Lakekeeper
  ├─ Install via Helm
  ├─ Configure Iceberg catalog
  └─ Create warehouses

Step 2: Develop Spark job
  ├─ bronze_transform.py
  ├─ Data quality checks
  └─ Iceberg table creation

Step 3: Create SparkApplication manifest
  ├─ Template for Airflow
  ├─ Configure resources
  └─ Test submission

Step 4: Deploy Spark Operator
  ├─ RBAC setup
  ├─ Test job submission
  └─ Verify table creation
```

### Phase 4: Airflow Orchestration (Week 4-5)

```bash
Step 1: Develop Airflow DAG
  ├─ data_ingestion.py
  ├─ Custom operators
  ├─ XCom passing
  └─ Error handling

Step 2: Deploy Airflow
  ├─ Configure executor
  ├─ Install providers
  └─ Add connections

Step 3: Test complete workflow
  ├─ Upload file
  ├─ Monitor Kafka
  ├─ Submit Spark job
  ├─ Verify Iceberg table
  └─ Check metrics

Step 4: Setup monitoring
  ├─ Prometheus
  ├─ Grafana dashboards
  └─ Alerting
```

### Phase 5: Production Hardening (Week 5-6)

```bash
Step 1: Error handling & retries
  ├─ Timeout handling
  ├─ Graceful degradation
  └─ Dead letter queues

Step 2: Data quality framework
  ├─ Schema validation
  ├─ Metrics tracking
  └─ Alerting

Step 3: Disaster recovery
  ├─ Backup strategy
  ├─ Data recovery procedures
  └─ Runbooks

Step 4: Documentation & training
  ├─ Setup guide
  ├─ Troubleshooting
  └─ Operations manual
```

---

## 6. Key Configuration Files

### 6.1 Kafka Topics

```yaml
# infra/k8s/kafka/kafka-topics.yaml

topics:
  - name: file-uploaded
    partitions: 3
    replication_factor: 2
    retention_ms: 604800000  # 7 days
    config:
      compression_type: snappy
      min_insync_replicas: 2
  
  - name: raw-data-ready
    partitions: 3
    replication_factor: 2
    retention_ms: 604800000
    config:
      compression_type: snappy
      min_insync_replicas: 2
  
  - name: bronze-layer-complete
    partitions: 1
    replication_factor: 2
    retention_ms: 2592000000  # 30 days
```

### 6.2 PostgreSQL Schema

```sql
-- Initialize database for Airflow + metrics

-- Job execution metrics
CREATE TABLE public.job_metrics (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL UNIQUE,
    table_name VARCHAR(255),
    input_records INTEGER,
    output_records INTEGER,
    rejected_records INTEGER,
    status VARCHAR(50),
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Data quality checks
CREATE TABLE public.data_quality_metrics (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    check_name VARCHAR(255),
    check_status VARCHAR(50),
    check_value TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (job_id) REFERENCES public.job_metrics(job_id)
);

-- Workflow execution
CREATE TABLE public.workflow_execution (
    id SERIAL PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    total_duration_seconds INTEGER,
    tasks_completed INTEGER,
    tasks_failed INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Table lineage (optional)
CREATE TABLE public.table_lineage (
    id SERIAL PRIMARY KEY,
    source_table VARCHAR(255),
    target_table VARCHAR(255),
    transformation_type VARCHAR(255),
    job_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_job_metrics_created_at ON public.job_metrics(created_at);
CREATE INDEX idx_job_metrics_job_id ON public.job_metrics(job_id);
CREATE INDEX idx_data_quality_job_id ON public.data_quality_metrics(job_id);
```

---

## 7. Deployment Commands

```bash
# Setup namespaces
kubectl create namespace data-platform
kubectl create namespace monitoring

# Deploy Kafka
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install kafka bitnami/kafka -f infra/k8s/kafka/helm-values.yaml -n data-platform
bash infra/k8s/kafka/scripts/create_topics.sh

# Deploy MinIO
helm install minio bitnami/minio -f infra/k8s/minio/helm-values.yaml -n data-platform
bash infra/k8s/minio/scripts/create_buckets.sh

# Deploy PostgreSQL
helm install postgresql bitnami/postgresql -f infra/k8s/postgresql/helm-values.yaml -n data-platform
kubectl exec -it postgresql-0 -n data-platform -- psql -U airflow -d airflow -f database-init.sql

# Deploy Lakekeeper
helm install lakekeeper lakekeeper/lakekeeper -f infra/k8s/lakekeeper/helm-values.yaml -n data-platform

# Deploy Spark Operator
helm install spark-operator spark-operator/spark-operator -f infra/k8s/spark-operator/helm-values.yaml -n data-platform

# Deploy NiFi
helm install nifi cetic/nifi -f infra/k8s/nifi/helm-values.yaml -n data-platform

# Deploy Airflow
helm install airflow apache-airflow/airflow -f infra/k8s/airflow/helm-values.yaml -n data-platform

# Verify all components
kubectl get pods -n data-platform
kubectl get svc -n data-platform
```

---

**Architecture Version**: 1.0 (No ArgoCD)  
**Status**: Ready for Implementation  
**Target Deployment**: Kubernetes 1.24+

---

