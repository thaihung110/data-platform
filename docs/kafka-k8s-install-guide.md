# Kafka Installation Guide for Kubernetes
## Data Lakehouse Project - Production Setup

---

## 📋 Table of Contents

1. [Introduction](#1-introduction)
2. [Architecture Decision](#2-architecture-decision)
3. [Prerequisites](#3-prerequisites)
4. [Installation Methods Comparison](#4-installation-methods-comparison)
5. [Method 1: Bitnami Helm Chart (Recommended)](#5-method-1-bitnami-helm-chart-recommended)
6. [Method 2: Strimzi Operator (Advanced)](#6-method-2-strimzi-operator-advanced)
7. [Post-Installation Configuration](#7-post-installation-configuration)
8. [Testing & Verification](#8-testing--verification)
9. [Production Best Practices](#9-production-best-practices)
10. [Troubleshooting](#10-troubleshooting)
11. [Monitoring & Metrics](#11-monitoring--metrics)

---

## 1. Introduction

### 1.1 Kafka trong Data Lakehouse Architecture

Trong project Data Lakehouse của chúng ta, Kafka đóng vai trò là **Event Bus** trong Orchestration Layer:

```
User Upload → Datasource API → Kafka (file-uploaded topic)
                                    ↓
                            Airflow Listener (consume)
                                    ↓
                            Trigger DAG (orchestration)
                                    ↓
                            NiFi (data ingestion)
                                    ↓
                            Kafka (raw-data-ready topic)
                                    ↓
                            Airflow (submit Spark job)
```

**Chức năng chính:**
- Event streaming giữa các components
- Trigger workflows trong Airflow
- Message bus cho data pipeline
- Decoupling giữa producers và consumers

### 1.2 KRaft Mode (Kafka Raft)

Từ Kafka 3.3.0+, Apache Kafka hỗ trợ **KRaft mode** - loại bỏ dependency vào ZooKeeper:

| Aspect | ZooKeeper Mode | KRaft Mode |
|--------|---------------|------------|
| **Architecture** | Kafka + ZooKeeper cluster | Kafka only (self-contained) |
| **Complexity** | Higher (2 systems) | Lower (1 system) |
| **Performance** | Good | Better (metadata handling) |
| **Recovery** | Slower | Faster |
| **Production Ready** | Yes (legacy) | Yes (Kafka 3.9.1+) |
| **Future** | Deprecated | Recommended |

**Recommendation:** Sử dụng **KRaft mode** cho project mới (2025+)

---

## 2. Architecture Decision

### 2.1 Kafka Cluster Configuration

Cho Data Lakehouse project, chúng ta sẽ setup:

```
┌─────────────────────────────────────────────────────────┐
│ KAFKA CLUSTER ARCHITECTURE (KRaft Mode)                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  CONTROLLER NODES (3 replicas)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Controller  │  │ Controller  │  │ Controller  │    │
│  │ kafka-ctrl- │  │ kafka-ctrl- │  │ kafka-ctrl- │    │
│  │ 0           │  │ 1           │  │ 2           │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│       ▲               ▲               ▲                 │
│       │               │               │                 │
│       └───────────────┴───────────────┘                 │
│              Raft Consensus                             │
│                                                          │
│  BROKER NODES (3 replicas)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Broker      │  │ Broker      │  │ Broker      │    │
│  │ kafka-0     │  │ kafka-1     │  │ kafka-2     │    │
│  │             │  │             │  │             │    │
│  │ Topics:     │  │ Topics:     │  │ Topics:     │    │
│  │ - file-up   │  │ - file-up   │  │ - file-up   │    │
│  │ - raw-ready │  │ - raw-ready │  │ - raw-ready │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Configuration:**
- **Controllers:** 3 nodes (quorum for metadata)
- **Brokers:** 3 nodes (data replication)
- **Replication Factor:** 2 (for topics)
- **Partitions:** 3 per topic (for parallelism)

### 2.2 Topics Configuration

```yaml
Topics Required:
  - file-uploaded
    Purpose: Datasource API publishes file metadata
    Partitions: 3
    Replication: 2
    Retention: 7 days
  
  - raw-data-ready
    Purpose: NiFi notifies raw data completion
    Partitions: 3
    Replication: 2
    Retention: 7 days
  
  - bronze-layer-complete
    Purpose: Spark job completion notification
    Partitions: 1
    Replication: 2
    Retention: 30 days
```

---

## 3. Prerequisites

### 3.1 System Requirements

```bash
# Kubernetes cluster
Kubernetes: 1.23+
kubectl: latest version
Helm: 3.8.0+

# Resource requirements (minimum)
Memory per pod:
  - Controller: 1Gi
  - Broker: 2Gi
  
CPU per pod:
  - Controller: 0.5 cores
  - Broker: 1 core

Storage per pod:
  - Controller: 8Gi (SSD recommended)
  - Broker: 20Gi (SSD recommended)
```

### 3.2 Verify Prerequisites

```bash
# 1. Check Kubernetes version
kubectl version --short

# Output should show:
# Client Version: v1.28.x
# Server Version: v1.28.x

# 2. Check Helm version
helm version

# Output should show:
# version.BuildInfo{Version:"v3.13.x", ...}

# 3. Check available nodes
kubectl get nodes

# Should show at least 3 nodes with Ready status

# 4. Check StorageClass
kubectl get storageclass

# Should show default StorageClass with provisioner
```

### 3.3 Create Namespace

```bash
# Create namespace for Kafka
kubectl create namespace data-platform

# Verify
kubectl get namespace data-platform

# Set as default namespace (optional)
kubectl config set-context --current --namespace=data-platform
```

---

## 4. Installation Methods Comparison

### 4.1 Method Comparison Table

| Aspect | Bitnami Helm Chart | Strimzi Operator |
|--------|-------------------|------------------|
| **Installation** | ✅ Simple (helm install) | ⚠️ Complex (CRDs + Operator) |
| **Configuration** | ✅ Values.yaml | ⚠️ Custom Resources |
| **KRaft Support** | ✅ Native | ✅ Native |
| **Topic Management** | Manual/Script | ✅ KafkaTopic CR |
| **User Management** | Manual | ✅ KafkaUser CR |
| **Monitoring** | Prometheus metrics | ✅ Prometheus + Grafana |
| **Production Ready** | ✅ Yes | ✅ Yes |
| **Learning Curve** | ✅ Low | ⚠️ High |
| **Best For** | Quick setup, MVP | Enterprise, GitOps |

### 4.2 Recommendation for This Project

**Choose Bitnami Helm Chart** ✅

**Reasons:**
1. Simpler setup (1 helm command)
2. Native KRaft support
3. Easy to customize via values.yaml
4. Sufficient for orchestration use case (not data streaming)
5. Can migrate to Strimzi later if needed

**Use Strimzi if:**
- Need declarative topic management (GitOps)
- Need advanced Kafka features (MirrorMaker, Connect)
- Have dedicated Kafka team

---

## 5. Method 1: Bitnami Helm Chart (Recommended)

### 5.1 Project Structure

```
infra/k8s/orchestration/kafka/
│
├── README.md
├── values-dev.yaml              # Development environment
├── values-prod.yaml             # Production environment
├── topics/
│   ├── file-uploaded.yaml
│   ├── raw-data-ready.yaml
│   └── bronze-layer-complete.yaml
│
├── scripts/
│   ├── install.sh               # Install Kafka
│   ├── uninstall.sh             # Remove Kafka
│   ├── create-topics.sh         # Create topics
│   ├── test-connectivity.sh     # Test connection
│   └── port-forward.sh          # Local access
│
└── monitoring/
    ├── prometheus-servicemonitor.yaml
    └── grafana-dashboard.json
```

### 5.2 Step 1: Add Bitnami Helm Repository

```bash
# Add Bitnami repository
helm repo add bitnami https://charts.bitnami.com/bitnami

# Update repositories
helm repo update

# Verify Kafka chart
helm search repo bitnami/kafka

# Output:
# NAME          	CHART VERSION	APP VERSION	DESCRIPTION
# bitnami/kafka 	30.1.6       	3.9.0      	Apache Kafka is a distributed streaming platform
```

### 5.3 Step 2: Create values-prod.yaml

```yaml
# infra/k8s/orchestration/kafka/values-prod.yaml

## ============================================================================
## GLOBAL CONFIGURATION
## ============================================================================

global:
  storageClass: "standard"  # Change to your StorageClass

## ============================================================================
## KAFKA CONFIGURATION (KRaft Mode)
## ============================================================================

# Enable KRaft mode (no ZooKeeper)
kraft:
  enabled: true

# Kafka image
image:
  registry: docker.io
  repository: bitnami/kafka
  tag: 3.9.0-debian-12-r1
  pullPolicy: IfNotPresent

# Resource allocation
controller:
  # Controller configuration (metadata management)
  replicaCount: 3
  
  resources:
    requests:
      memory: 1Gi
      cpu: 500m
    limits:
      memory: 2Gi
      cpu: 1000m
  
  # Persistence for controller
  persistence:
    enabled: true
    storageClass: "standard"
    size: 8Gi
  
  # Affinity to spread across nodes
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: kafka
              app.kubernetes.io/component: controller
          topologyKey: kubernetes.io/hostname

broker:
  # Broker configuration (data handling)
  replicaCount: 3
  
  resources:
    requests:
      memory: 2Gi
      cpu: 1000m
    limits:
      memory: 4Gi
      cpu: 2000m
  
  # Persistence for broker
  persistence:
    enabled: true
    storageClass: "standard"
    size: 20Gi
  
  # Affinity to spread across nodes
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: kafka
              app.kubernetes.io/component: broker
          topologyKey: kubernetes.io/hostname

## ============================================================================
## LISTENERS CONFIGURATION
## ============================================================================

listeners:
  client:
    protocol: PLAINTEXT
    name: CLIENT
    containerPort: 9092
    svcPort: 9092
  
  controller:
    protocol: PLAINTEXT
    name: CONTROLLER
    containerPort: 9093
  
  interbroker:
    protocol: PLAINTEXT
    name: INTERNAL
    containerPort: 9094

# Advertised listeners
advertisedListeners:
  - "CLIENT://kafka:9092"

## ============================================================================
## KAFKA SERVER CONFIGURATION
## ============================================================================

config:
  # Auto create topics (disable for production)
  auto.create.topics.enable: "false"
  
  # Default replication factor
  default.replication.factor: "2"
  min.insync.replicas: "2"
  
  # Leader election
  unclean.leader.election.enable: "false"
  
  # Log retention
  log.retention.hours: "168"  # 7 days
  log.retention.bytes: "1073741824"  # 1GB
  log.segment.bytes: "536870912"  # 512MB
  
  # Compression
  compression.type: "snappy"
  
  # Performance tuning
  num.network.threads: "3"
  num.io.threads: "8"
  socket.send.buffer.bytes: "102400"
  socket.receive.buffer.bytes: "102400"
  socket.request.max.bytes: "104857600"
  
  # Replication
  replica.lag.time.max.ms: "30000"
  replica.socket.timeout.ms: "30000"
  replica.fetch.max.bytes: "1048576"

## ============================================================================
## PROVISIONING (Topic Creation)
## ============================================================================

provisioning:
  enabled: true
  replicationFactor: 2
  numPartitions: 3
  
  topics:
    - name: file-uploaded
      partitions: 3
      replicationFactor: 2
      config:
        retention.ms: "604800000"  # 7 days
        compression.type: "snappy"
        max.message.bytes: "1048576"  # 1MB
    
    - name: raw-data-ready
      partitions: 3
      replicationFactor: 2
      config:
        retention.ms: "604800000"  # 7 days
        compression.type: "snappy"
        max.message.bytes: "1048576"
    
    - name: bronze-layer-complete
      partitions: 1
      replicationFactor: 2
      config:
        retention.ms: "2592000000"  # 30 days
        compression.type: "snappy"
        max.message.bytes: "1048576"

## ============================================================================
## SECURITY
## ============================================================================

# Authentication (SASL disabled for internal cluster)
auth:
  clientProtocol: plaintext
  interBrokerProtocol: plaintext

# TLS disabled for development (enable for production)
tls:
  enabled: false

## ============================================================================
## METRICS & MONITORING
## ============================================================================

metrics:
  kafka:
    enabled: true
  
  jmx:
    enabled: true
  
  serviceMonitor:
    enabled: true
    namespace: data-platform
    labels:
      prometheus: kube-prometheus

## ============================================================================
## SERVICE
## ============================================================================

service:
  type: ClusterIP
  ports:
    client: 9092
  
  # Headless service for StatefulSet
  headless:
    enabled: true

## ============================================================================
## RESOURCE LIMITS (Production)
## ============================================================================

# Pod Disruption Budget
pdb:
  create: true
  minAvailable: 2

# Network Policies (optional)
networkPolicy:
  enabled: false

## ============================================================================
## VOLUME CONFIGURATION
## ============================================================================

volumePermissions:
  enabled: true

## ============================================================================
## LOGGING
## ============================================================================

logLevel: INFO

## ============================================================================
## ADDITIONAL CONFIGURATION
## ============================================================================

# Environment variables
extraEnvVars:
  - name: KAFKA_HEAP_OPTS
    value: "-Xmx2G -Xms2G"
  - name: KAFKA_JVM_PERFORMANCE_OPTS
    value: "-XX:+UseG1GC -XX:MaxGCPauseMillis=20 -XX:InitiatingHeapOccupancyPercent=35"
```

### 5.4 Step 3: Create Installation Script

```bash
# infra/k8s/orchestration/kafka/scripts/install.sh

#!/bin/bash

set -e

echo "🚀 Installing Kafka on Kubernetes..."

# Configuration
NAMESPACE="data-platform"
RELEASE_NAME="kafka"
VALUES_FILE="../values-prod.yaml"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if namespace exists
echo -e "${YELLOW}📍 Checking namespace...${NC}"
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo -e "${YELLOW}Creating namespace: $NAMESPACE${NC}"
    kubectl create namespace "$NAMESPACE"
else
    echo -e "${GREEN}✅ Namespace $NAMESPACE exists${NC}"
fi

# Add Bitnami repository
echo -e "${YELLOW}📦 Adding Bitnami Helm repository...${NC}"
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install Kafka
echo -e "${YELLOW}🔧 Installing Kafka with Helm...${NC}"
helm install "$RELEASE_NAME" bitnami/kafka \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --wait \
    --timeout 10m

# Wait for pods to be ready
echo -e "${YELLOW}⏳ Waiting for Kafka pods to be ready...${NC}"
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=kafka \
    -n "$NAMESPACE" \
    --timeout=300s

# Get status
echo -e "${YELLOW}📊 Kafka status:${NC}"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=kafka

# Get service
echo -e "${YELLOW}🌐 Kafka service:${NC}"
kubectl get svc -n "$NAMESPACE" -l app.kubernetes.io/name=kafka

# Display connection info
echo -e "${GREEN}✅ Kafka installation completed!${NC}"
echo ""
echo -e "${YELLOW}Connection Information:${NC}"
echo "  Kafka Bootstrap Server: kafka.data-platform.svc.cluster.local:9092"
echo "  Namespace: $NAMESPACE"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Create topics: bash scripts/create-topics.sh"
echo "  2. Test connectivity: bash scripts/test-connectivity.sh"
echo "  3. Check logs: kubectl logs -n $NAMESPACE kafka-broker-0"
```

### 5.5 Step 4: Create Topic Management Script

```bash
# infra/k8s/orchestration/kafka/scripts/create-topics.sh

#!/bin/bash

set -e

echo "📝 Creating Kafka Topics..."

NAMESPACE="data-platform"
KAFKA_POD="kafka-broker-0"
BOOTSTRAP_SERVER="kafka:9092"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to create topic
create_topic() {
    local topic_name=$1
    local partitions=$2
    local replication_factor=$3
    local retention_ms=$4
    
    echo -e "${YELLOW}Creating topic: $topic_name${NC}"
    
    kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh \
            --create \
            --if-not-exists \
            --bootstrap-server "$BOOTSTRAP_SERVER" \
            --topic "$topic_name" \
            --partitions "$partitions" \
            --replication-factor "$replication_factor" \
            --config retention.ms="$retention_ms" \
            --config compression.type=snappy \
            --config max.message.bytes=1048576
    
    echo -e "${GREEN}✅ Topic $topic_name created${NC}"
}

# Wait for Kafka to be ready
echo -e "${YELLOW}⏳ Waiting for Kafka to be ready...${NC}"
kubectl wait --for=condition=ready pod -n "$NAMESPACE" "$KAFKA_POD" --timeout=180s

# Create topics
echo ""
echo -e "${YELLOW}Creating topics...${NC}"

# file-uploaded topic
create_topic "file-uploaded" 3 2 604800000  # 7 days

# raw-data-ready topic
create_topic "raw-data-ready" 3 2 604800000  # 7 days

# bronze-layer-complete topic
create_topic "bronze-layer-complete" 1 2 2592000000  # 30 days

# List all topics
echo ""
echo -e "${YELLOW}📋 All topics:${NC}"
kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
    kafka-topics.sh \
        --list \
        --bootstrap-server "$BOOTSTRAP_SERVER"

# Describe topics
echo ""
echo -e "${YELLOW}📊 Topic details:${NC}"
for topic in "file-uploaded" "raw-data-ready" "bronze-layer-complete"; do
    echo ""
    echo -e "${YELLOW}Topic: $topic${NC}"
    kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh \
            --describe \
            --bootstrap-server "$BOOTSTRAP_SERVER" \
            --topic "$topic"
done

echo ""
echo -e "${GREEN}✅ All topics created successfully!${NC}"
```

### 5.6 Step 5: Run Installation

```bash
# Navigate to kafka directory
cd infra/k8s/orchestration/kafka/

# Make scripts executable
chmod +x scripts/*.sh

# Install Kafka
bash scripts/install.sh

# Wait for installation to complete (5-10 minutes)

# Verify installation
kubectl get pods -n data-platform -l app.kubernetes.io/name=kafka

# Expected output:
# NAME                  READY   STATUS    RESTARTS   AGE
# kafka-controller-0    1/1     Running   0          5m
# kafka-controller-1    1/1     Running   0          5m
# kafka-controller-2    1/1     Running   0          5m
# kafka-broker-0        1/1     Running   0          5m
# kafka-broker-1        1/1     Running   0          5m
# kafka-broker-2        1/1     Running   0          5m

# Create topics (if not auto-created)
bash scripts/create-topics.sh
```

---

## 6. Method 2: Strimzi Operator (Advanced)

### 6.1 When to Use Strimzi

Use Strimzi if you need:
- ✅ Declarative topic management (GitOps)
- ✅ Built-in user management (KafkaUser CR)
- ✅ Advanced features (MirrorMaker, Connect, Bridge)
- ✅ Kubernetes-native operations

### 6.2 Installation Steps

```bash
# 1. Install Strimzi Operator
kubectl create namespace kafka
helm install strimzi-operator strimzi/strimzi-kafka-operator -n kafka

# 2. Create Kafka Cluster CR
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: data-lakehouse-kafka
  namespace: data-platform
spec:
  kafka:
    version: 3.9.0
    replicas: 3
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      offsets.topic.replication.factor: 2
      transaction.state.log.replication.factor: 2
      transaction.state.log.min.isr: 2
      default.replication.factor: 2
      min.insync.replicas: 2
    storage:
      type: persistent-claim
      size: 20Gi
  entityOperator:
    topicOperator: {}
    userOperator: {}
EOF

# 3. Create Topics via KafkaTopic CR
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: file-uploaded
  namespace: data-platform
  labels:
    strimzi.io/cluster: data-lakehouse-kafka
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000
    compression.type: snappy
EOF
```

---

## 7. Post-Installation Configuration

### 7.1 Verify Installation

```bash
# Check pods
kubectl get pods -n data-platform -l app.kubernetes.io/name=kafka

# Check services
kubectl get svc -n data-platform -l app.kubernetes.io/name=kafka

# Check persistent volumes
kubectl get pvc -n data-platform

# Check logs
kubectl logs -n data-platform kafka-broker-0 --tail=50

# Check Kafka cluster info
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-broker-api-versions.sh \
        --bootstrap-server kafka:9092
```

### 7.2 Create Connection ConfigMap

```yaml
# infra/k8s/orchestration/kafka/kafka-connection-config.yaml

apiVersion: v1
kind: ConfigMap
metadata:
  name: kafka-connection
  namespace: data-platform
data:
  KAFKA_BOOTSTRAP_SERVERS: "kafka.data-platform.svc.cluster.local:9092"
  KAFKA_SECURITY_PROTOCOL: "PLAINTEXT"
  KAFKA_SASL_MECHANISM: "NONE"
  
  # Topic names
  KAFKA_TOPIC_FILE_UPLOADED: "file-uploaded"
  KAFKA_TOPIC_RAW_DATA_READY: "raw-data-ready"
  KAFKA_TOPIC_BRONZE_COMPLETE: "bronze-layer-complete"
  
  # Consumer groups
  KAFKA_CONSUMER_GROUP_AIRFLOW: "airflow-data-ingestion"
  KAFKA_CONSUMER_GROUP_MONITORING: "monitoring-consumers"
```

Apply:
```bash
kubectl apply -f kafka-connection-config.yaml
```

---

## 8. Testing & Verification

### 8.1 Test Producer-Consumer

```bash
# infra/k8s/orchestration/kafka/scripts/test-connectivity.sh

#!/bin/bash

set -e

NAMESPACE="data-platform"
KAFKA_POD="kafka-broker-0"
BOOTSTRAP_SERVER="kafka:9092"
TEST_TOPIC="test-topic"

echo "🧪 Testing Kafka connectivity..."

# Create test topic
echo "1. Creating test topic..."
kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
    kafka-topics.sh \
        --create \
        --if-not-exists \
        --bootstrap-server "$BOOTSTRAP_SERVER" \
        --topic "$TEST_TOPIC" \
        --partitions 1 \
        --replication-factor 1

# Produce test message
echo "2. Producing test message..."
echo "Hello Kafka at $(date)" | kubectl exec -i -n "$NAMESPACE" "$KAFKA_POD" -- \
    kafka-console-producer.sh \
        --bootstrap-server "$BOOTSTRAP_SERVER" \
        --topic "$TEST_TOPIC"

# Consume test message
echo "3. Consuming test message..."
kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
    kafka-console-consumer.sh \
        --bootstrap-server "$BOOTSTRAP_SERVER" \
        --topic "$TEST_TOPIC" \
        --from-beginning \
        --max-messages 1 \
        --timeout-ms 5000

# Delete test topic
echo "4. Cleaning up test topic..."
kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- \
    kafka-topics.sh \
        --delete \
        --bootstrap-server "$BOOTSTRAP_SERVER" \
        --topic "$TEST_TOPIC"

echo "✅ Kafka connectivity test passed!"
```

Run test:
```bash
bash scripts/test-connectivity.sh
```

### 8.2 Test from External Pod

```bash
# Deploy test pod
kubectl run kafka-test-client \
    --image=bitnami/kafka:3.9.0 \
    --namespace=data-platform \
    --command -- sleep infinity

# Produce message
kubectl exec -n data-platform kafka-test-client -- \
    kafka-console-producer.sh \
        --bootstrap-server kafka:9092 \
        --topic file-uploaded \
        <<< '{"filename":"test.csv","size":1024}'

# Consume message
kubectl exec -n data-platform kafka-test-client -- \
    kafka-console-consumer.sh \
        --bootstrap-server kafka:9092 \
        --topic file-uploaded \
        --from-beginning \
        --max-messages 1

# Clean up
kubectl delete pod kafka-test-client -n data-platform
```

### 8.3 Test with Python Client

```python
# test_kafka_python.py

from confluent_kafka import Producer, Consumer
import json

# Producer test
def test_producer():
    producer = Producer({
        'bootstrap.servers': 'kafka.data-platform.svc.cluster.local:9092'
    })
    
    message = {
        'filename': 'test_orders.csv',
        'size': 2048,
        'timestamp': '2025-01-15T14:00:00Z'
    }
    
    producer.produce(
        'file-uploaded',
        key='test',
        value=json.dumps(message).encode('utf-8')
    )
    
    producer.flush()
    print("✅ Message produced successfully")

# Consumer test
def test_consumer():
    consumer = Consumer({
        'bootstrap.servers': 'kafka.data-platform.svc.cluster.local:9092',
        'group.id': 'test-consumer-group',
        'auto.offset.reset': 'earliest'
    })
    
    consumer.subscribe(['file-uploaded'])
    
    msg = consumer.poll(timeout=5.0)
    
    if msg is None:
        print("❌ No message received")
    else:
        print(f"✅ Message received: {msg.value().decode('utf-8')}")
    
    consumer.close()

if __name__ == '__main__':
    test_producer()
    test_consumer()
```

---

## 9. Production Best Practices

### 9.1 Resource Management

```yaml
# Production resource recommendations

controller:
  resources:
    requests:
      memory: 2Gi      # Minimum for production
      cpu: 1000m
    limits:
      memory: 4Gi
      cpu: 2000m

broker:
  resources:
    requests:
      memory: 4Gi      # Minimum for production
      cpu: 2000m
    limits:
      memory: 8Gi
      cpu: 4000m
```

### 9.2 Storage Configuration

```yaml
# Use SSD storage class for better performance
persistence:
  storageClass: "ssd"  # or "gp3" on AWS
  size: 100Gi          # Scale based on retention
```

### 9.3 High Availability

```yaml
# Pod Disruption Budget
pdb:
  create: true
  minAvailable: 2      # Always maintain 2 brokers

# Pod Anti-Affinity
podAntiAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          app: kafka
      topologyKey: kubernetes.io/hostname
```

### 9.4 Security Hardening

```yaml
# Enable TLS for production
tls:
  enabled: true
  autoGenerated: true
  
# Enable SASL authentication
auth:
  clientProtocol: sasl_ssl
  interBrokerProtocol: sasl_ssl
  sasl:
    mechanism: scram-sha-512
```

### 9.5 Backup Strategy

```bash
# Backup Kafka topics metadata
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-topics.sh \
        --bootstrap-server kafka:9092 \
        --describe \
        --all > kafka-topics-backup.txt

# Backup persistent volumes (use Velero)
velero backup create kafka-backup \
    --include-namespaces data-platform \
    --selector app.kubernetes.io/name=kafka
```

---

## 10. Troubleshooting

### 10.1 Common Issues

#### Issue 1: Pods Not Starting

```bash
# Check pod status
kubectl get pods -n data-platform -l app.kubernetes.io/name=kafka

# Check pod events
kubectl describe pod kafka-broker-0 -n data-platform

# Check logs
kubectl logs kafka-broker-0 -n data-platform --tail=100

# Common causes:
# - Insufficient resources
# - Storage class not available
# - Image pull errors
```

#### Issue 2: Topics Not Creating

```bash
# Verify broker is ready
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-broker-api-versions.sh \
        --bootstrap-server kafka:9092

# Check auto.create.topics.enable
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-configs.sh \
        --bootstrap-server kafka:9092 \
        --describe \
        --entity-type brokers \
        --all

# Manually create topic
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-topics.sh \
        --create \
        --bootstrap-server kafka:9092 \
        --topic test \
        --partitions 1 \
        --replication-factor 1
```

#### Issue 3: Connection Refused

```bash
# Check service endpoints
kubectl get endpoints kafka -n data-platform

# Test connection from test pod
kubectl run -it --rm debug \
    --image=busybox \
    --namespace=data-platform \
    -- sh

# Inside pod:
nc -zv kafka 9092

# Check network policies
kubectl get networkpolicies -n data-platform
```

### 10.2 Debug Commands

```bash
# Get Kafka cluster info
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-metadata.sh \
        --bootstrap-server kafka:9092 \
        describe --all

# Check consumer groups
kubectl exec -n data-platform kafka-broker-0 -- \
    kafka-consumer-groups.sh \
        --bootstrap-server kafka:9092 \
        --list

# Check broker logs
kubectl logs -n data-platform kafka-broker-0 --tail=500 | grep ERROR

# Check controller logs
kubectl logs -n data-platform kafka-controller-0 --tail=500
```

---

## 11. Monitoring & Metrics

### 11.1 Prometheus Metrics

Kafka exposes JMX metrics via Prometheus exporter:

```yaml
# prometheus-servicemonitor.yaml

apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kafka-metrics
  namespace: data-platform
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: kafka
  endpoints:
    - port: metrics
      interval: 30s
```

### 11.2 Key Metrics to Monitor

```
# Broker metrics
kafka_server_replicamanager_partitioncount
kafka_server_replicamanager_underreplicatedpartitions
kafka_server_brokertopicmetrics_messagesinpersec
kafka_server_brokertopicmetrics_bytesinpersec

# Consumer lag
kafka_consumergroup_lag
kafka_consumergroup_lag_seconds

# Network metrics
kafka_network_requestmetrics_requestspersec
kafka_network_requestmetrics_totaltimems
```

### 11.3 Grafana Dashboard

Use Kafka dashboard ID: **7589**

```bash
# Import to Grafana
https://grafana.com/grafana/dashboards/7589-kafka-overview/
```

---

## 12. Maintenance & Operations

### 12.1 Upgrade Kafka

```bash
# Update values.yaml with new version
image:
  tag: 3.10.0-debian-12-r1

# Upgrade via Helm
helm upgrade kafka bitnami/kafka \
    --namespace data-platform \
    --values values-prod.yaml \
    --wait

# Verify upgrade
kubectl get pods -n data-platform -l app.kubernetes.io/name=kafka
```

### 12.2 Scale Brokers

```bash
# Edit values.yaml
broker:
  replicaCount: 5  # Increase from 3 to 5

# Apply changes
helm upgrade kafka bitnami/kafka \
    --namespace data-platform \
    --values values-prod.yaml

# Verify
kubectl get pods -n data-platform | grep kafka-broker
```

### 12.3 Cleanup & Uninstall

```bash
# infra/k8s/orchestration/kafka/scripts/uninstall.sh

#!/bin/bash

set -e

NAMESPACE="data-platform"
RELEASE_NAME="kafka"

echo "🗑️  Uninstalling Kafka..."

# Delete Helm release
helm uninstall "$RELEASE_NAME" -n "$NAMESPACE"

# Delete PVCs (optional - data will be lost!)
read -p "Delete persistent volumes? (y/N): " confirm
if [[ $confirm == [yY] ]]; then
    kubectl delete pvc -n "$NAMESPACE" -l app.kubernetes.io/name=kafka
    echo "✅ PVCs deleted"
fi

echo "✅ Kafka uninstalled"
```

---

## 13. Integration with Data Lakehouse Components

### 13.1 Airflow Integration

```python
# airflow-dags/dags/config/kafka_config.py

KAFKA_CONFIG = {
    'bootstrap_servers': 'kafka.data-platform.svc.cluster.local:9092',
    'topics': {
        'file_uploaded': 'file-uploaded',
        'raw_data_ready': 'raw-data-ready',
        'bronze_complete': 'bronze-layer-complete'
    },
    'consumer_group': 'airflow-data-ingestion',
    'security_protocol': 'PLAINTEXT'
}
```

### 13.2 NiFi Integration

```xml
<!-- NiFi ConsumeKafka Processor -->
<property>
  <name>Bootstrap Servers</name>
  <value>kafka.data-platform.svc.cluster.local:9092</value>
</property>
<property>
  <name>Topic Name</name>
  <value>file-uploaded</value>
</property>
<property>
  <name>Group ID</name>
  <value>nifi-consumers</value>
</property>
```

### 13.3 Datasource API Integration

```python
# datasource-api/kafka_producer.py

from confluent_kafka import Producer
import json

producer = Producer({
    'bootstrap.servers': 'kafka.data-platform.svc.cluster.local:9092'
})

def publish_upload_event(filename, size, upload_path):
    message = {
        'filename': filename,
        'size': size,
        'upload_path': upload_path,
        'timestamp': datetime.now().isoformat()
    }
    
    producer.produce(
        'file-uploaded',
        key=filename,
        value=json.dumps(message).encode('utf-8')
    )
    
    producer.flush()
```

---

## 14. Summary

### 14.1 Quick Reference

```bash
# Installation
helm install kafka bitnami/kafka -f values-prod.yaml -n data-platform

# Create topics
bash scripts/create-topics.sh

# Test connectivity
bash scripts/test-connectivity.sh

# Check status
kubectl get pods -n data-platform -l app.kubernetes.io/name=kafka

# View logs
kubectl logs -n data-platform kafka-broker-0 -f

# Uninstall
helm uninstall kafka -n data-platform
```

### 14.2 Connection Strings

```
Internal (within cluster):
  kafka.data-platform.svc.cluster.local:9092

Localhost (with port-forward):
  localhost:9092

External (with LoadBalancer):
  <EXTERNAL-IP>:9092
```

### 14.3 Next Steps

1. ✅ Install Kafka (completed)
2. ⏭️ Install NiFi
3. ⏭️ Install Airflow
4. ⏭️ Configure Datasource API
5. ⏭️ Test end-to-end workflow

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-15  
**Kafka Version:** 3.9.0  
**Helm Chart:** bitnami/kafka 30.1.6  
**Status:** Production Ready ✅
