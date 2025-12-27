# Data Platform

A comprehensive data platform built on Kubernetes for ingesting, processing, and managing data using modern data engineering tools.

## Project Structure

```
data-platform/
├── airflow/                    # Airflow DAGs and custom operators
│   ├── dags/                  # DAG definitions
│   │   ├── csv_ingestion_listener_dag.py
│   │   └── taxi_data_ingestion_dag.py
│   └── src/ingestion/         # Custom modules
│       ├── kafka_sensor.py
│       ├── nifi_client.py
│       └── message_models.py
│
├── source-api/                # FastAPI CSV upload service
│   ├── app/                   # Application code
│   ├── kubernetes/            # K8s deployment manifests
│   └── Dockerfile
│
├── spark-jobs/                # Spark job implementations
│   ├── taxi_data_ingestion/  # Taxi data processing job
│   └── build-image.sh         # Docker image build script
│
├── infra/k8s/                 # Kubernetes infrastructure
│   ├── storage/               # MinIO, PostgreSQL, Keycloak, Lakekeeper
│   ├── orchestration/         # Kafka, NiFi, Airflow
│   ├── ingestion/             # Source API deployment
│   └── compute/               # Spark Operator, Argo CD
│
├── docs/                      # Documentation
│   ├── airflow-git-sync-ssh-setup.md
│   ├── NIFI-CSV-TO-PARQUET.md
│   └── AIRFLOW-TAXI-INGESTION-DAG.md
│
└── assets/                    # Screenshots and images
```

## Components

### Data Ingestion Layer

**Source API** (FastAPI)

- REST API for CSV file uploads
- Chunks large files for processing
- Publishes metadata to Kafka topic `csv-ingestion`
- Stores chunks in persistent storage

**Kafka** (Bitnami)

- Message broker for event streaming
- SASL authentication enabled
- Topics: `csv-ingestion`
- KRaft mode (no Zookeeper)

**NiFi** (Apache NiFi)

- Data flow automation
- Consumes Kafka messages
- Downloads CSV chunks from Source API
- Converts CSV to Parquet format
- Uploads to MinIO raw bucket

### Storage Layer

**MinIO** (Object Storage)

- S3-compatible object storage
- Buckets: `raw`, `bronze`, `silver`, `gold`
- Stores Parquet files and Iceberg tables

**PostgreSQL** (Bitnami)

- Relational database for metadata
- Databases: `keycloak`, `catalog`, `openfga`, `source_api`
- Primary and read replicas

**Lakekeeper** (Iceberg Catalog)

- Apache Iceberg REST catalog
- Manages table metadata and schemas
- Integrates with Keycloak for authentication
- Warehouses: `bronze`, `silver`, `gold`

**Keycloak** (Identity & Access Management)

- OAuth2/OIDC authentication
- Realm: `iceberg`
- Clients: `lakekeeper`, `spark`
- User management and RBAC

**OpenFGA** (Authorization)

- Fine-grained access control
- Integrates with Lakekeeper

### Orchestration Layer

**Airflow** (Apache Airflow)

- Workflow orchestration
- DAGs for data pipelines
- Git-Sync for DAG deployment from private GitHub repo
- KubernetesPodOperator for Spark job submission

**Kafka UI** (Provectus)

- Web UI for Kafka cluster management
- Topic monitoring and message inspection

### Compute Layer

**Spark Operator** (Kubeflow)

- Manages Spark applications on Kubernetes
- Custom Resource Definitions (CRDs)
- Automatic driver/executor pod management

**Argo CD** (GitOps)

- Continuous deployment
- Manages Kubernetes resources
- Git-based configuration

## Data Flow

### CSV Ingestion Pipeline

1. **Upload**: User uploads CSV file to Source API
2. **Chunk**: Source API splits CSV into chunks
3. **Publish**: Metadata published to Kafka `csv-ingestion` topic
4. **Trigger**: Airflow DAG detects Kafka message and triggers NiFi
5. **Process**: NiFi downloads chunks, converts to Parquet
6. **Store**: Parquet files uploaded to MinIO `raw` bucket

### Taxi Data Ingestion Pipeline

1. **Schedule**: Airflow DAG runs hourly
2. **Submit**: DAG submits Spark job to Kubernetes
3. **Read**: Spark reads Parquet files from MinIO `raw` bucket
4. **Transform**: Data cleaning and deduplication
5. **Write**: Writes to Iceberg table in Lakekeeper `bronze` warehouse
6. **Catalog**: Lakekeeper manages table metadata

## Quick Start

### Prerequisites

- Kubernetes cluster (Minikube, Kind, or cloud provider)
- kubectl configured
- Helm 3.x installed
- Docker for building images

### Deployment Order

1. **Storage Layer**

   ```bash
   cd infra/k8s/storage
   ./scripts/install_postgresql.sh
   ./scripts/install_minio.sh
   ./scripts/install_keycloak.sh
   ./scripts/install_openfga.sh
   ./scripts/install_lakekeeper.sh
   ```

2. **Orchestration Layer**

   ```bash
   cd infra/k8s/orchestration
   ./scripts/install_kafka.sh
   ./scripts/install_kafka_ui.sh
   ./scripts/install_nifi.sh
   ./scripts/install_airflow.sh

   # Apply RBAC for Spark jobs
   kubectl apply -f rbac/spark-submit-clusterrole.yaml
   kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml
   ```

3. **Ingestion Layer**

   ```bash
   cd infra/k8s/ingestion
   ./scripts/install_source_api.sh
   ```

4. **Compute Layer**
   ```bash
   cd infra/k8s/compute
   ./scripts/install_spark_operators.sh
   ./scripts/install_argocd.sh
   ```

### Access URLs

| Service       | URL                               | Credentials             |
| ------------- | --------------------------------- | ----------------------- |
| Airflow       | https://openhouse.airflow.test    | admin / admin           |
| Kafka UI      | https://openhouse.kafka-ui.test   | No auth                 |
| NiFi          | https://openhouse.nifi.test       | admin / adminadminadmin |
| Keycloak      | https://openhouse.keycloak.test   | admin / admin           |
| Lakekeeper    | https://openhouse.lakekeeper.test | admin / admin           |
| MinIO Console | http://localhost:9001             | admin / admin123        |

**Note**: Add hostnames to `/etc/hosts` or configure DNS
