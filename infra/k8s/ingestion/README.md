# Data Ingestion

This directory contains ingestion applications for collecting data from external sources and sending it to Kafka.

## Directory Structure

```
ingestion/
├── application/          # Kubernetes manifests for ingestion applications
│   └── source-api.yaml
├── scripts/             # Installation and management scripts
│   ├── install_source_api.sh
│   └── uninstall_source_api.sh
└── README.md           # This documentation
```

## Application

### Source API

FastAPI REST API for uploading and processing CSV files, splitting them into chunks, and publishing metadata to Kafka.

**Configuration:**

- **Kafka Topic**: `csv-ingestion`
- **Kafka Server**: `openhouse-kafka:9092`
- **Database**: PostgreSQL (`source_api` database)
- **Storage**: PersistentVolume (10Gi) for CSV chunks
- **Namespace**: `default`

**Features:**

- Upload CSV files via REST API
- Split CSV into chunks (by size or rows)
- Store chunks in persistent storage
- Publish metadata to Kafka
- Health and readiness endpoints
- Database persistence for tracking uploads

## Deployment

### Prerequisites

1. **Kafka cluster** deployed (see `infra/k8s/orchestration/`)
2. **PostgreSQL database** created with `source_api` database (see `infra/k8s/storage/config/postgresql.yaml`)
3. **Docker image** `fastapi-csv-uploader:latest` built and available
4. **Kafka topic** `csv-ingestion` created

### Build Docker Image

Build from the `source-api` directory:

```bash
cd ../source-api
docker build -t fastapi-csv-uploader:latest .

# If using a registry
docker tag fastapi-csv-uploader:latest your-registry/fastapi-csv-uploader:latest
docker push your-registry/fastapi-csv-uploader:latest
```

Update the image in `application/source-api.yaml` if using a registry.

### Create Kafka Topic

Create the `csv-ingestion` topic using the provided script:

```bash
cd infra/k8s/ingestion
./scripts/create_kafka_topics_sasl.sh
```

This script creates the topic with SASL authentication and the following configuration:

**Topic Configuration:**

- **Topic Name**: `csv-ingestion`
- **Partitions**: 3 (scalable based on needs)
- **Replication Factor**: 1 (increase if multiple brokers available)
- **SASL Authentication**: PLAIN mechanism with admin credentials
- **Bootstrap Server**: `localhost:9092` (from within Kafka pod)

### Install

```bash
cd infra/k8s/ingestion
./scripts/install_source_api.sh
```

Or apply directly:

```bash
kubectl apply -f application/source-api.yaml
```

### Uninstall

```bash
cd infra/k8s/ingestion
./scripts/uninstall_source_api.sh
```

The script will prompt to confirm deletion of the PersistentVolumeClaim.

## Monitoring

### Check Status

```bash
# Deployment status
kubectl get deployment fastapi-csv-uploader -n default

# Pods
kubectl get pods -n default -l app=fastapi-csv-uploader

# Service
kubectl get svc fastapi-csv-uploader -n default

# PVC
kubectl get pvc csv-chunks-pvc -n default
```

### View Logs

```bash
# Real-time logs
kubectl logs -f deployment/fastapi-csv-uploader -n default

# Specific pod logs
kubectl logs -n default -l app=fastapi-csv-uploader --tail=100
```

### Test API Endpoints

```bash
# Port-forward for local testing
kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000

# From another terminal
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready

# Test CSV upload (requires a CSV file)
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@test.csv" \
  -F "dataset_name=my_dataset" \
  -F "chunk_size=50" \
  -F "chunk_type=size"
```

## Troubleshooting

### Pod Not Starting

```bash
# Check events
kubectl describe pod -n default -l app=fastapi-csv-uploader

# View logs
kubectl logs -n default -l app=fastapi-csv-uploader
```

### PVC Not Binding

```bash
# Check PVC status
kubectl describe pvc csv-chunks-pvc -n default

# View available PVs
kubectl get pv
```

### Database Connection Issues

```bash
# Test connection from pod
kubectl exec -it deployment/fastapi-csv-uploader -n default -- \
  python -c "import psycopg2; conn = psycopg2.connect(host='openhouse-postgresql-primary', port=5432, database='source_api', user='source_api', password='source_api'); print('✅ Connected!')"
```

### Kafka Publishing Issues

```bash
# Check Kafka service
kubectl get svc openhouse-kafka -n default

# Describe topic
kubectl exec -it -n default openhouse-kafka-0 -- \
  kafka-topics.sh --describe --bootstrap-server localhost:9092 --topic csv-ingestion

# Consume messages to verify
kubectl exec -it -n default openhouse-kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic csv-ingestion --from-beginning
```

## API Documentation

After deployment, access Swagger UI:

```bash
# Port-forward
kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000

# Open in browser
http://localhost:8000/docs
```

## Resources

- **Memory**: 128Mi request, 512Mi limit
- **CPU**: 100m request, 500m limit
- **Storage**: 10Gi PersistentVolume
- **Replicas**: 1
