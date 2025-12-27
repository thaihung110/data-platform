# Orchestration Infrastructure

This directory manages orchestration components including Airflow, Kafka, NiFi, and Kafka UI on Kubernetes using Helm.

## Directory Structure

- `helm/`: Pulled Helm charts (e.g., `helm/airflow`, `helm/kafka`, `helm/nifi`)
- `config/`: Customized values files (e.g., `config/airflow.yaml`, `config/kafka.yaml`)
- `scripts/`: Installation and uninstallation scripts
- `test_template/`: Template output for testing Helm rendering

---

## Configuration Changes from Defaults

### Airflow Custom Configuration

**File**: `config/airflow.yaml`

#### Ingress Configuration

```yaml
ingress:
  hosts:
    - name: "openhouse.airflow.test" # Hostname for accessing Airflow UI
      tls:
        enabled: false # Disable TLS, use HTTP (enable for production with certificates)
  ingressClassName: "nginx" # Use nginx ingress controller
```

**Git-Sync SSH Setup**:

1. Generate SSH key pair: `ssh-keygen -t rsa -b 4096 -C "your_email@example.com" -f ~/.ssh/airflow-git-sync -N ""`
2. Add public key (`~/.ssh/airflow-git-sync.pub`) to GitHub repository Deploy Keys
3. Convert private key to base64: `base64 ~/.ssh/airflow-git-sync -w 0`
4. Add the base64 string to `extraSecrets.airflow-ssh-secret.data` in `airflow.yaml`
5. Git-Sync will clone the repository every 60 seconds and sync DAGs automatically

#### Git-Sync for DAGs (SSH Authentication)

```yaml
extraSecrets:
  airflow-ssh-secret:
    data: <your-base64-encoded-ssh-private-key> # Base64 encoded SSH private key for GitHub access

dags:
  gitSync:
    enabled: true # Enable Git-Sync sidecar container
    repo: git@github.com:<your-username>/<your-repo>.git # SSH URL of your private GitHub repository
    branch: main # Git branch to sync from
    rev: HEAD # Git revision to checkout (HEAD = latest)
    subPath: "path/to/dags/folder" # Subdirectory containing DAG files within the repo
    sshKeySecret: airflow-ssh-secret # Reference to the SSH secret created above
```

#### Database Configuration

```yaml
data:
  metadataConnection:
    user: postgres # PostgreSQL username
    pass: postgres # PostgreSQL password
    protocol: postgresql # Database protocol
    host: openhouse-airflow-postgresql # PostgreSQL service name (created by subchart)
    port: 5432 # PostgreSQL port
    db: postgres # Database name for Airflow metadata
    sslmode: disable # Disable SSL for database connection (enable for production)
```

#### Storage Class

```yaml
storageClassName: <your-storage-class> # Kubernetes StorageClass for PVCs (e.g., "standard", "gp2", "local-path")
```

**Note**: Update `storageClassName` in both PostgreSQL and Redis persistence sections.

---

### Kafka Custom Configuration

**File**: `config/kafka.yaml`

#### Storage Class

```yaml
defaultStorageClass: <your-storage-class-name> # Default StorageClass for all Kafka PVCs
```

#### Client Listener with SASL Authentication

```yaml
listeners:
  client:
    containerPort: 9092 # Port for client connections
    protocol: SASL_PLAINTEXT # Enable SASL authentication with plaintext transport (no encryption)
    name: CLIENT # Listener name
    sslClientAuth: "" # No SSL client authentication required
```

**Protocol Explanation**:

- `SASL_PLAINTEXT`: Enables username/password authentication without TLS encryption
- Use `SASL_SSL` for production to add encryption
- `PLAINTEXT` would disable authentication entirely

#### SASL User Configuration

```yaml
sasl:
  client:
    users:
      - user1 # First SASL user
      - admin # Second SASL user (admin account)
    passwords: "user1,admin" # Comma-separated passwords matching users order
```

**SASL Mechanism**: PLAIN (username/password authentication)
**Connection String Example**: `bootstrap-servers=openhouse-kafka:9092` with SASL properties

#### Image Repository Change

```yaml
image:
  # Use bitnami legacy repository instead of default bitnami
  repository: bitnamilegacy/kafka
  repository: bitnamilegacy/os-shell
  repository: bitnamilegacy/kubectl
  repository: bitnamilegacy/jmx-exporter
```

**Reason**: The legacy repository provides more stable images for specific Kafka versions. Update all Bitnami chart dependencies to use `bitnamilegacy` repository.

#### Single-Node Configuration (Override Settings)

```yaml
overrideConfiguration:
  offsets.topic.replication.factor: 1 # Set __consumer_offsets topic replication to 1 (default is 3, fails with single broker)
  transaction.state.log.replication.factor: 1 # Set transaction log replication to 1 (default is 3)
  transaction.state.log.min.isr: 1 # Minimum in-sync replicas for transaction log (must be <= replication factor)
```

**Purpose**: These settings are **critical for single-node Kafka clusters**. Default replication factor of 3 causes broker crash and consumer offset errors when running only 1 broker.

**Global Override** (applies to all brokers/controllers):

- `offsets.topic.replication.factor: 1` - Internal `__consumer_offsets` topic uses 1 replica
- `transaction.state.log.replication.factor: 1` - Transaction state log uses 1 replica
- `transaction.state.log.min.isr: 1` - Minimum 1 replica must be in-sync

#### Controller Configuration (Combined Mode)

```yaml
controller:
  replicaCount: 1 # Number of controller replicas
  controllerOnly: false # Run controller+broker in same process (combined mode, not dedicated)
  overrideConfiguration:
    offsets.topic.replication.factor: 1 # Controller-specific override
    transaction.state.log.replication.factor: 1
    transaction.state.log.min.isr: 1
```

**Combined Mode (`controllerOnly: false`)**:

- Controllers also act as brokers (single process for both roles)
- Saves resources in development/small deployments
- Set to `true` for dedicated controllers in production

#### Broker Configuration (Disabled for Combined Mode)

```yaml
broker:
  replicaCount: 0 # No dedicated brokers when using combined mode (controllerOnly: false)
```

**Note**: When `controller.controllerOnly: false`, set `broker.replicaCount: 0` to avoid duplicate broker processes. Controllers handle both metadata and message processing.

---

### Kafka UI Custom Configuration

**File**: `config/kafka-ui.yaml`

#### Application Configuration with SASL

```yaml
existingConfigMap: "" # Don't use external ConfigMap, define inline

yamlApplicationConfig:
  kafka:
    clusters:
      - name: openhouse-kafka # Display name in UI
        bootstrapServers: openhouse-kafka:9092 # Kafka service endpoint
        properties:
          security.protocol: SASL_PLAINTEXT # Match Kafka listener protocol
          sasl.mechanism: PLAIN # Use PLAIN SASL mechanism
          sasl.jaas.config: org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin"; # SASL credentials for connecting to Kafka
  auth:
    type: disabled # Disable authentication for Kafka UI itself (enable LOGIN/OAUTH2 for production)
  management:
    health:
      ldap:
        enabled: false # Disable LDAP health check
```

#### Ingress Configuration

```yaml
ingress:
  enabled: true # Enable ingress for external access
  annotations: {} # Optional ingress annotations
  ingressClassName: "nginx" # Use nginx ingress controller
  path: "/" # Root path
  pathType: "Prefix" # Match all paths with this prefix
  host: "openhouse.kafka-ui.test" # Hostname for accessing Kafka UI
```

**Access**: Visit `https://openhouse.kafka-ui.test` in browser (requires DNS/hosts configuration)

---

### NiFi Custom Configuration

**File**: `config/nifi.yaml`

#### Ingress Configuration

```yaml
ingress:
  enabled: true # Enable ingress for external access
  className: nginx # Use nginx ingress controller
  annotations:
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS" # NiFi uses HTTPS backend
    nginx.ingress.kubernetes.io/ssl-redirect: "false" # Don't force HTTPS redirect (HTTP to NiFi HTTPS)
  tls: [] # No TLS termination at ingress (NiFi handles HTTPS internally)
  hosts: ["openhouse.nifi.test"] # Hostname for accessing NiFi UI
  path: / # Root path
```

#### Web Proxy Configuration

```yaml
properties:
  webProxyHost: openhouse.nifi.test # Must match ingress hostname for proper URL generation
```

**Purpose**: NiFi uses `webProxyHost` to generate correct callback URLs and links in the UI when accessed through a proxy/ingress.

#### Single User Authentication

```yaml
auth:
  singleUser:
    username: admin # Admin username
    password: adminadminadmin # Admin password (must be at least 12 characters)
```

**Note**: NiFi requires passwords to be at least 12 characters long for single-user authentication mode.

#### NiFi Processor Group: CSV to Parquet Ingestion

**Purpose**: Process CSV chunks from Source API and upload as Parquet files to MinIO raw bucket.

**Prerequisites**:

- MinIO `raw` bucket created (use MinIO UI: Console → Buckets → Create Bucket)
- Source API deployed and producing messages to `csv-ingestion` Kafka topic
- Kafka SASL authentication enabled

**Flow Architecture**:

```
ConsumeKafka → EvaluateJsonPath → InvokeHTTP → ConvertRecord → UpdateAttribute → PutS3Object
```

**Processor 1: ConsumeKafka_2_6**

| Property              | Value                  | Description                      |
| --------------------- | ---------------------- | -------------------------------- |
| **Kafka Brokers**     | `openhouse-kafka:9092` | Internal Kafka service           |
| **Topic Name(s)**     | `csv-ingestion`        | Source API topic                 |
| **Group ID**          | `nifi-csv-consumer`    | Consumer group                   |
| **Offset Reset**      | `earliest`             | Start from beginning             |
| **Security Protocol** | `SASL_PLAINTEXT`       | Enable SASL authentication       |
| **SASL Mechanism**    | `PLAIN`                | Username/password authentication |
| **Username**          | `admin`                | SASL username                    |
| **Password**          | `admin`                | SASL password                    |
| **Max Poll Records**  | `100`                  | Batch size                       |

**Processor 2: EvaluateJsonPath**

Extract metadata from Kafka message to flowfile attributes:

| Custom Property  | JSON Path        | Extracted Value   |
| ---------------- | ---------------- | ----------------- |
| **api_endpoint** | `$.api_endpoint` | CSV download URL  |
| **upload_id**    | `$.upload_id`    | Upload identifier |
| **dataset_name** | `$.dataset_name` | Dataset name      |
| **chunk_id**     | `$.chunk_id`     | Chunk number      |

**Processor 3: InvokeHTTP**

| Property               | Value             | Description         |
| ---------------------- | ----------------- | ------------------- |
| **HTTP Method**        | `GET`             | Download CSV        |
| **Remote URL**         | `${api_endpoint}` | From Kafka message  |
| **Connection Timeout** | `30 sec`          | Wait for connection |

**Processor 4: ConvertRecord**

Requires two **Controller Services**:

1. **CSVReader**:

   - Schema Access Strategy: `Infer Schema`
   - Treat First Line as Header: `true`
   - CSV Format: `Custom Format`

2. **ParquetRecordSetWriter**:
   - Compression Type: `SNAPPY`
   - Schema Access Strategy: `Inherit Record Schema`

**Processor 5: UpdateAttribute**

Set S3 path attributes:

| Custom Property | Value                                                              | Purpose        |
| --------------- | ------------------------------------------------------------------ | -------------- |
| **s3.bucket**   | `raw`                                                              | MinIO bucket   |
| **s3.key**      | `${dataset_name}/upload_id=${upload_id}/chunk_${chunk_id}.parquet` | S3 object path |
| **filename**    | `chunk_${chunk_id}.parquet`                                        | File name      |

**Processor 6: PutS3Object**

| Property                  | Value               | Description            |
| ------------------------- | ------------------- | ---------------------- |
| **Bucket**                | `${s3.bucket}`      | From UpdateAttribute   |
| **Object Key**            | `${s3.key}`         | S3 path                |
| **Region**                | `us-east-1`         | Required (any value)   |
| **Access Key ID**         | `admin`             | MinIO credentials      |
| **Secret Access Key**     | `admin123`          | MinIO password         |
| **Endpoint Override URL** | `http://minio:9000` | Internal MinIO service |
| **Signer Override**       | `AWSS3V4SignerType` | S3v4 signing           |

**Important Notes**:

- Create `raw` bucket in MinIO before starting the flow
- Use internal service name `http://minio:9000` (not localhost)
- SASL credentials must match Kafka configuration (`admin/admin`)
- Final file path: `raw/{dataset_name}/upload_id={upload_id}/chunk_{chunk_id}.parquet`

---

## RBAC Configuration for Airflow

**Purpose**: Grant Airflow workers permission to submit and monitor Spark jobs on Kubernetes.

**Location**: `rbac/`

### ClusterRole: spark-submit-role

Defines permissions required for Airflow to manage Spark jobs:

**Permissions**:

- **SparkApplications**: Create, get, list, watch, update, patch, delete
- **Pods**: Get, list, watch (for monitoring Spark driver/executor pods)
- **Pods/log**: Get, list, watch (for retrieving Spark logs)
- **Services**: Get, list (for Spark UI service)
- **ConfigMaps**: Get, list (if SparkApplication needs ConfigMaps)

**File**: `rbac/spark-submit-clusterrole.yaml`

### ClusterRoleBinding: spark-submit-binding

Binds the ClusterRole to Airflow service accounts:

**Subjects**:

1. `openhouse-spark-operator-spark` (namespace: default) - For submitting Spark jobs via KubernetesPodOperator
2. `openhouse-airflow-worker` (namespace: default) - For monitoring Spark jobs with SparkKubernetesSensor in worker pods

**File**: `rbac/spark-submit-clusterrolebinding.yaml`

### Apply RBAC

```bash
cd infra/k8s/orchestration

# Apply ClusterRole
kubectl apply -f rbac/spark-submit-clusterrole.yaml

# Apply ClusterRoleBinding
kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml

# Verify
kubectl get clusterrole spark-submit-role
kubectl get clusterrolebinding spark-submit-binding
```

**Note**: These RBAC resources must be applied before running Airflow DAGs that submit Spark jobs.

---

## Deployment Instructions

### Deploy Airflow

```bash
cd infra/k8s/orchestration
./scripts/install_airflow.sh
```

Account: admin/admin

### Deploy Kafka

```bash
cd infra/k8s/orchestration
./scripts/install_kafka.sh
```

### Deploy Kafka UI

```bash
cd infra/k8s/orchestration
./scripts/install_kafka_ui.sh
```

### Deploy NiFi

```bash
cd infra/k8s/orchestration
./scripts/install_nifi.sh
```

Account: admin/adminadminadmin

---

## Uninstallation

### Uninstall Airflow

```bash
cd infra/k8s/orchestration
./scripts/uninstall_airflow.sh
```

### Uninstall Kafka

```bash
cd infra/k8s/orchestration
./scripts/uninstall_kafka.sh
```

### Uninstall Kafka UI

```bash
cd infra/k8s/orchestration
./scripts/uninstall_kafka_ui.sh
```

### Uninstall NiFi

```bash
cd infra/k8s/orchestration
./scripts/uninstall_nifi.sh
```

---

## Access URLs

| Service    | URL                             | Credentials             |
| ---------- | ------------------------------- | ----------------------- |
| Airflow UI | https://openhouse.airflow.test  | admin / admin           |
| Kafka UI   | https://openhouse.kafka-ui.test | No authentication       |
| NiFi UI    | https://openhouse.nifi.test     | admin / adminadminadmin |

**Note**: Add these hostnames to your `/etc/hosts` file or configure DNS:

```
<your-ingress-ip> openhouse.airflow.test
<your-ingress-ip> openhouse.kafka-ui.test
<your-ingress-ip> openhouse.nifi.test
```

---

## Important Configuration Notes

### Storage Classes

All components require a valid Kubernetes StorageClass. Update the following in each config file:

- **Airflow**: `postgresql.primary.persistence.storageClass`, `redis.persistence.storageClassName`, `worker.persistence.storageClassName`, `triggerer.persistence.storageClassName`, `dags.persistence.storageClassName`, `logs.persistence.storageClassName`
- **Kafka**: `defaultStorageClass`
- **NiFi**: Check NiFi chart values for persistence configuration

- `standard` (default in many clusters)
- `gp2` (AWS EBS)
- `local-path` (local development)

### Ingress Controller

All services use `nginx` ingress class. Ensure nginx-ingress-controller is installed:

```bash
kubectl get pods -n ingress-nginx
```

### SASL Authentication for Kafka

Clients connecting to Kafka must provide SASL credentials:

```properties
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";
```

---

## Troubleshooting

### Airflow Git-Sync Issues

Check git-sync container logs:

```bash
kubectl logs deployment/openhouse-airflow-scheduler -c git-sync -n default
```

Verify SSH secret:

```bash
kubectl get secret airflow-ssh-secret -n default
```

### Kafka SASL Connection Failures

Test SASL authentication from a Kafka pod:

```bash
kubectl exec -it openhouse-kafka-broker-0 -n default -- kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic test-topic \
  --consumer.config /tmp/client.properties
```

### NiFi Proxy Issues

Ensure `webProxyHost` in `config/nifi.yaml` matches the ingress hostname exactly.

### Ingress Not Working

Check ingress controller status:

```bash
kubectl get pods -n ingress-nginx
kubectl get ingress -A
```
