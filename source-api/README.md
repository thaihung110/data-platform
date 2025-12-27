# Source API - Testing Guide

FastAPI service để upload CSV files, tự động chia chunks và publish metadata lên Kafka.

## Quick Start

### 1. Deploy Source API

```bash
cd infra/k8s/ingestion

# Create Kafka topic
./scripts/create_source_api_topic.sh

# Deploy application
./scripts/install_source_api.sh
```

### 2. Port Forward

```bash
kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000
```

### 3. Test API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Expected: {"status":"healthy","timestamp":"..."}
```

---

## Upload CSV

### Basic Upload

```bash
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi" \
  -F "chunk_type=rows" \
  -F "chunk_rows=100" \
  | jq '.'
```

**Response:**

```json
{
  "upload_id": "abc-xyz-123",
  "dataset_name": "taxi",
  "total_chunks": 3,
  "chunk_size": 100,
  "chunk_unit": "rows",
  "status": "processing",
  "created_at": "2025-12-23T10:00:00"
}
```

### Chunking Options

**By Rows** (recommended cho CSV lớn):

```bash
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi" \
  -F "chunk_type=rows" \
  -F "chunk_rows=100"
```

**By Size** (MB):

```bash
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi" \
  -F "chunk_type=size" \
  -F "chunk_size=50"
```

---

## Download Chunks

### Step 1: Get Chunk Filename

```bash
UPLOAD_ID="abc-xyz-123"  # From upload response

# List chunks
kubectl exec deployment/fastapi-csv-uploader -n default -- \
  ls -lh /tmp/csv-chunks/${UPLOAD_ID}/
```

### Step 2: Download via API

```bash
UPLOAD_ID="abc-xyz-123"
FILENAME="taxi_1_1766483513.csv"

curl -o downloaded.csv \
  "http://localhost:8000/api/v1/chunks/${UPLOAD_ID}/${FILENAME}/download"
```

### Auto Download Script

```bash
#!/bin/bash
UPLOAD_ID="$1"

# Get all filenames
FILES=$(kubectl exec deployment/fastapi-csv-uploader -n default -- \
  ls /tmp/csv-chunks/${UPLOAD_ID}/)

# Download each
for FILE in $FILES; do
  curl -o "$FILE" \
    "http://localhost:8000/api/v1/chunks/${UPLOAD_ID}/${FILE}/download"
  echo "Downloaded: $FILE"
done
```

Usage:

```bash
chmod +x download_chunks.sh
./download_chunks.sh abc-xyz-123
```

---

## Verify Kafka Messages

Chunks metadata được publish lên Kafka topic `csv-ingestion`.

```bash
# Consume 1 message
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic csv-ingestion \
    --from-beginning \
    --max-messages 1
```

**Message Format:**

```json
{
  "upload_id": "abc-xyz-123",
  "dataset_name": "taxi",
  "chunk_id": 1,
  "filename": "taxi_1_1766483513.csv",
  "chunk_size_mb": 0.26,
  "file_path": "/tmp/csv-chunks/abc-xyz-123/taxi_1_1766483513.csv",
  "headers": ["VendorID", "tpep_pickup_datetime", ...],
  "api_endpoint": "http://fastapi-csv-uploader:8000/chunks/abc-xyz-123/taxi_1_1766483513.csv/download"
}
```

**NiFi Integration:** NiFi consume messages và download từ `api_endpoint`.

---

## Complete Test Workflow

```bash
# 1. Port forward (terminal 1)
kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000

# 2. Upload (terminal 2)
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi" \
  -F "chunk_type=rows" \
  -F "chunk_rows=100")

echo $RESPONSE | jq '.'

# 3. Extract upload_id
UPLOAD_ID=$(echo $RESPONSE | jq -r '.upload_id')
echo "Upload ID: $UPLOAD_ID"

# 4. Check Kafka
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic csv-ingestion \
    --from-beginning \
    --max-messages 1

# 5. List chunks
kubectl exec deployment/fastapi-csv-uploader -n default -- \
  ls -lh /tmp/csv-chunks/${UPLOAD_ID}/

# 6. Download first chunk
FILENAME=$(kubectl exec deployment/fastapi-csv-uploader -n default -- \
  ls /tmp/csv-chunks/${UPLOAD_ID}/ | head -n 1)

curl -o downloaded.csv \
  "http://localhost:8000/api/v1/chunks/${UPLOAD_ID}/${FILENAME}/download"

# 7. Verify
head -5 downloaded.csv
wc -l downloaded.csv
```

---

## API Documentation

Swagger UI:

```bash
# Open browser
http://localhost:8000/docs
```

---

## Troubleshooting

### Pod không start

```bash
kubectl logs deployment/fastapi-csv-uploader -n default
kubectl describe pod -l app=fastapi-csv-uploader -n default
```

### Upload failed

```bash
# Check logs
kubectl logs -f deployment/fastapi-csv-uploader -n default

# Check PVC space
kubectl exec deployment/fastapi-csv-uploader -n default -- df -h /tmp/csv-chunks
```

### Kafka không nhận messages

```bash
# List topics
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-topics.sh --list --bootstrap-server localhost:9092

# Describe topic
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-topics.sh --describe --bootstrap-server localhost:9092 --topic csv-ingestion
```

---

## Monitoring

```bash
# Logs
kubectl logs -f deployment/fastapi-csv-uploader -n default

# Pod status
kubectl get pods -l app=fastapi-csv-uploader -n default

# PVC usage
kubectl get pvc csv-chunks-pvc -n default
```

---

## Cleanup

```bash
cd infra/k8s/ingestion
./scripts/uninstall_source_api.sh
```
