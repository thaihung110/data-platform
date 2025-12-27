# Airflow Data Ingestion Platform

## 📁 Project Structure

```
airflow/
├── dags/
│   ├── csv_ingestion_listener_dag.py    # Kafka → NiFi pipeline
│   └── taxi_data_ingestion_dag.py       # MinIO → Iceberg pipeline
│
├── src/ingestion/
│   ├── config.py                        # 🆕 Environment variable config
│   ├── kafka_sensor.py                  # 🆕 Custom Kafka sensor
│   ├── kafka_listeners.py               # Message extraction
│   ├── nifi_client.py                   # NiFi REST API client
│   └── message_models.py                # Pydantic data models
│
├── .env.example                         # 🆕 Example environment config
└── docs/
    └── csv-ingestion-listener-setup.md
```

## 🔄 Git-Sync Setup for DAG Deployment

### Overview

Instead of manually copying DAGs to Airflow pods, use Git-Sync to automatically sync DAGs from a private GitHub repository.

### Prerequisites

- Private GitHub repository for Airflow DAGs
- SSH access to GitHub
- Airflow deployed on Kubernetes with Helm

### Step 1: Create Private Repository

Create a new private repository on GitHub for your Airflow DAGs:

```bash
# Option 1: GitHub Web UI
# Visit: https://github.com/new
# Repository name: airflow-dags
# Visibility: Private

# Option 2: GitHub CLI
gh repo create airflow-dags --private
```

### Step 2: Push DAGs to Repository

```bash
cd airflow

# Initialize git (if not already)
git init
git add dags/
git commit -m "Initial DAGs"

# Add remote and push
git remote add origin git@github.com:<your-username>/airflow-dags.git
git branch -M main
git push -u origin main
```

### Step 3: Generate SSH Key

```bash
# Generate SSH key pair
ssh-keygen -t rsa -b 4096 -C "your_email@example.com" -f ~/.ssh/airflow-git-sync -N ""

# Output:
# Private key: ~/.ssh/airflow-git-sync
# Public key: ~/.ssh/airflow-git-sync.pub
```

### Step 4: Add Deploy Key to GitHub

```bash
# Copy public key
cat ~/.ssh/airflow-git-sync.pub

# Add to GitHub:
# 1. Go to: https://github.com/<your-username>/airflow-dags/settings/keys
# 2. Click "Add deploy key"
# 3. Title: "Airflow Git-Sync"
# 4. Paste public key
# 5. Click "Add key"
```

### Step 5: Convert Private Key to Base64

```bash
# Convert private key to base64
base64 ~/.ssh/airflow-git-sync -w 0 > /tmp/private-key-base64.txt

# Copy the base64 string
cat /tmp/private-key-base64.txt
```

### Step 6: Update Airflow Configuration

Edit `infra/k8s/orchestration/config/airflow.yaml`:

```yaml
dags:
  persistence:
    enabled: false # Disable persistence, use Git-Sync instead

  gitSync:
    enabled: true
    repo: git@github.com:<your-username>/airflow-dags.git # Your repository SSH URL
    branch: main
    rev: HEAD
    depth: 1
    maxFailures: 0
    subPath: "dags" # Subdirectory containing DAG files
    sshKeySecret: airflow-ssh-secret
    period: 60s # Sync interval
    wait: 60

# Create secret with SSH private key
extraSecrets:
  airflow-ssh-secret:
    data: |
      gitSshKey: '<paste-base64-private-key-here>'  # Paste base64 string from Step 5
```

### Step 7: Upgrade Airflow

```bash
cd infra/k8s/orchestration

# Upgrade Helm release
./scripts/install_airflow.sh

# Or manually:
helm upgrade openhouse-airflow helm/airflow \
  -n default \
  -f config/airflow.yaml \
  --timeout 10m
```

### Step 8: Verify Git-Sync

```bash
# Check secret created
kubectl get secret airflow-ssh-secret -n default

# View git-sync logs
SCHEDULER_POD=$(kubectl get pods -n default -l component=scheduler -o jsonpath='{.items[0].metadata.name}')
kubectl logs $SCHEDULER_POD -n default -c git-sync --tail=30

# Check DAGs synced
kubectl exec -it $SCHEDULER_POD -n default -c scheduler -- \
  ls -la /opt/airflow/dags/repo/dags/

# Expected output:
# csv_ingestion_listener_dag.py
# taxi_data_ingestion_dag.py
```

### Successful Git-Sync Logs

```
INFO: syncing from "git@github.com:<your-username>/airflow-dags.git"
INFO: cloning into "/tmp/git"
INFO: synced 2 files from "origin/main"
```

### Troubleshooting

**Permission denied (publickey)**:

```bash
# Test SSH connection
ssh -T git@github.com -i ~/.ssh/airflow-git-sync

# Expected: Hi <username>! You've successfully authenticated...
```

**Repository not found**:

```bash
# Verify repository exists
git clone git@github.com:<your-username>/airflow-dags.git /tmp/test-clone
```

**Failed to decode secret**:

```bash
# Regenerate base64 without line breaks
base64 ~/.ssh/airflow-git-sync -w 0 > /tmp/key.txt

# Verify decode works
base64 -d /tmp/key.txt | head -5
# Should show: -----BEGIN OPENSSH PRIVATE KEY-----
```

### Benefits of Git-Sync

- ✅ Automatic DAG updates (no manual deployment)
- ✅ Version control for DAGs
- ✅ Secure SSH authentication
- ✅ No GitHub rate limits
- ✅ Sync every 60 seconds

### Reference

For detailed setup guide, see: [docs/airflow-git-sync-ssh-setup.md](../docs/airflow-git-sync-ssh-setup.md)

## 🚀 DAGs Overview

### 1. CSV Ingestion Listener (`csv-ingestion-listener`)

**Purpose**: Event-driven pipeline that listens to Kafka and triggers NiFi processing

**Workflow**:

```
Kafka Topic (csv-ingestion) → Validate Message → Trigger NiFi Process Group
```

**Key Features**:

- ✅ **Environment Variable Configuration** (no Airflow UI setup needed)
- ✅ Kafka SASL authentication
- ✅ Pydantic message validation
- ✅ NiFi REST API integration
- ✅ Event-driven (no schedule)
- ✅ Parallel processing (max 5 concurrent runs)

**Tasks**:

1. `listen_kafka_csv_topic` - Custom Kafka sensor with confluent-kafka
2. `extract_message_data` - Validate and extract message
3. `trigger_nifi_process_group` - Trigger NiFi via REST API

**Configuration**: See [Environment Configuration](#environment-configuration) below

---

### 2. Taxi Data Ingestion (`taxi-data-ingestion`)

**Purpose**: Scheduled pipeline that processes taxi data from MinIO to Iceberg

**Workflow**:

```
MinIO (Parquet) → Spark Job (K8s) → Lakekeeper (Iceberg)
```

**Key Features**:

- ✅ Hourly schedule
- ✅ KubernetesPodOperator for Spark jobs
- ✅ Data deduplication
- ✅ Iceberg table management

**Tasks**:

1. `run_spark_ingestion` - Submit Spark job to K8s
2. Data cleaning and deduplication
3. Write to Iceberg bronze table

**Configuration**:

- **Schedule**: Hourly (`0 * * * *`)
- **Namespace**: K8s namespace for Spark jobs
- **Source**: MinIO bucket `raw`
- **Target**: Lakekeeper Iceberg warehouse

**Prerequisites for Spark Jobs**:

Before running the `taxi-data-ingestion` DAG, you must apply RBAC resources to grant Airflow permission to submit and monitor Spark jobs:

```bash
cd infra/k8s/orchestration

# Apply ClusterRole (defines permissions)
kubectl apply -f rbac/spark-submit-clusterrole.yaml

# Apply ClusterRoleBinding (grants permissions to service accounts)
kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml

# Verify RBAC resources
kubectl get clusterrole spark-submit-role
kubectl get clusterrolebinding spark-submit-binding
```

**Why RBAC is Required**:

- Airflow workers need permission to create and manage `SparkApplication` resources
- Workers need to monitor Spark driver/executor pods and retrieve logs
- Without RBAC, the DAG will fail with permission errors

For detailed RBAC configuration, see: [infra/k8s/orchestration/README.md](../infra/k8s/orchestration/README.md#rbac-configuration-for-airflow)

## ⚙️ Environment Configuration

### CSV Ingestion Listener (No Airflow UI Setup Required!)

All configuration is loaded from environment variables. See [`.env.example`](.env.example) for template.

**Required Variables**:

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=openhouse-kafka:9092
KAFKA_TOPIC_CSV_INGESTION=csv-ingestion
KAFKA_CONSUMER_GROUP_ID=airflow-csv-ingestion-consumer
KAFKA_SASL_USERNAME=admin
KAFKA_SASL_PASSWORD=admin
KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT
KAFKA_SASL_MECHANISM=PLAIN

# NiFi
NIFI_API_BASE_URL=https://openhouse-nifi:8443/nifi-api
NIFI_PROCESS_GROUP_ID=4be3c5be-019b-1000-4ef1-949cbb8c08de
NIFI_VERIFY_SSL=false
```

### Local Development

```bash
# Copy example file
cp .env.example .env

# Edit with your values
nano .env

# Load environment
export $(cat .env | xargs)
```

---

## 🔧 Core Modules

### `src/ingestion/config.py`

```python
class Config:
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_TOPIC_CSV_INGESTION: str
    NIFI_API_BASE_URL: str
    NIFI_PROCESS_GROUP_ID: str
    # ... loads from env vars
```

### `src/ingestion/kafka_sensor.py`

```python
class KafkaCSVIngestionSensor(BaseSensorOperator):
    # Custom sensor using confluent-kafka
    # No Airflow Connection needed
```

### `src/ingestion/kafka_listeners.py`

```python
def listen_for_csv_messages(message_content: str) -> Optional[Dict]
def extract_message_data(**context) -> Dict
```

### `src/ingestion/nifi_client.py`

```python
def trigger_nifi_process_group(**context) -> Dict
    # Uses requests library with environment config
    # No Airflow Connection/Variable needed
```

---

## ⚙️ Setup Requirements

### Python Dependencies

```
apache-airflow>=2.7.0
apache-airflow-providers-cncf-kubernetes
pydantic>=2.0.0
confluent-kafka
```

---

## 📖 Usage Examples

### Import Modules

```python
from ingestion.config import config
from ingestion.kafka_sensor import KafkaCSVIngestionSensor
from ingestion.nifi_client import trigger_nifi_process_group
```

### Create Kafka Sensor

```python
listen_task = KafkaCSVIngestionSensor(
    task_id="listen_kafka",
    poke_interval=config.KAFKA_POKE_INTERVAL,
    timeout=60 * 60 * 6,
)
```

### Trigger NiFi

```python
trigger_task = PythonOperator(
    task_id="trigger_nifi",
    python_callable=trigger_nifi_process_group,
)
```

---

## 🧪 Testing

### Test Config Loading

```python
from ingestion.config import config

print(f"Kafka: {config.KAFKA_BOOTSTRAP_SERVERS}")
print(f"NiFi: {config.NIFI_API_BASE_URL}")
```

### Test Kafka Sensor

```python
import os
os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'test:9092'

from ingestion.kafka_sensor import KafkaCSVIngestionSensor
sensor = KafkaCSVIngestionSensor(task_id='test')
# Verify configuration
```
