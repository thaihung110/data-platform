# NiFi Flow: CSV to Parquet Ingestion

Hướng dẫn cấu hình NiFi flow để consume CSV chunks từ Source API Kafka topic và upload lên MinIO as Parquet files.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [MinIO Setup](#minio-setup)
- [NiFi Flow Configuration](#nifi-flow-configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Flow Architecture

```
┌─────────────────┐
│  Kafka Topic    │
│ csv-ingestion   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ConsumeKafka    │  ← 1. Consume Kafka messages
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│EvaluateJsonPath │  ← 2. Extract metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  InvokeHTTP     │  ← 3. Download CSV chunk
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ConvertRecord   │  ← 4. CSV → Parquet
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│UpdateAttribute  │  ← 5. Set S3 path
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PutS3Object    │  ← 6. Upload to MinIO
└─────────────────┘
```

### Data Flow

1. Kafka message chứa metadata về CSV chunk
2. Extract `api_endpoint`, `upload_id`, `dataset_name`, `chunk_id`
3. Download CSV từ Source API
4. Convert CSV to Parquet (SNAPPY compression)
5. Set S3 path: `raw/{dataset_name}/upload_id={upload_id}/chunk_{chunk_id}.parquet`
6. Upload file lên MinIO

---

## Prerequisites

### 1. Source API Running

```bash
# Check Source API
kubectl get pods -l app=fastapi-csv-uploader -n default
kubectl logs -f deployment/fastapi-csv-uploader -n default
```

### 2. Kafka Topic Exists

```bash
# Verify topic
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-topics.sh --list --bootstrap-server localhost:9092 | grep csv-ingestion
```

### 3. NiFi Deployed

```bash
# Check NiFi
kubectl get pods -l app=nifi -n default

# Access NiFi UI
kubectl port-forward -n default svc/nifi 8443:8443
# Open: https://localhost:8443/nifi
```

### 4. MinIO Deployed

```bash
# Check MinIO
kubectl get pods -l app.kubernetes.io/name=minio -n default

# Access MinIO UI
kubectl port-forward -n default svc/minio 9000:9000 9001:9001
# Console: http://localhost:9001
```

---

## MinIO Setup

### Create Raw Bucket

**Option 1: Using MinIO Client (mc)**

```bash
# Port-forward MinIO
kubectl port-forward -n default svc/minio 9000:9000 &

# Configure mc
mc alias set local http://localhost:9000 admin admin123

# Create bucket
mc mb local/raw

# Verify
mc ls local/
```

**Option 2: Using MinIO Web Console**

1. Open http://localhost:9001
2. Login: `admin` / `admin123`
3. Click **Buckets** → **Create Bucket**
4. Bucket Name: `raw`
5. Click **Create**

### Verify Bucket

```bash
mc ls local/raw/
# Should be empty initially
```

---

## NiFi Flow Configuration

### Access NiFi UI

```bash
kubectl port-forward -n default svc/nifi 8443:8443
```

Open browser: https://localhost:8443/nifi

**Default credentials:** Check NiFi deployment logs for auto-generated password.

---

## Processor 1: ConsumeKafka_2_6

### Add Processor

1. Drag **Processor** icon onto canvas
2. Filter: `ConsumeKafka`
3. Select: **ConsumeKafka_2_6**
4. Click **Add**

### Configure Properties

| Property                 | Value                  | Description              |
| ------------------------ | ---------------------- | ------------------------ |
| **Kafka Brokers**        | `openhouse-kafka:9092` | Internal Kafka service   |
| **Topic Name(s)**        | `csv-ingestion`        | Source API topic         |
| **Topic Name Format**    | `names`                | Use topic names          |
| **Group ID**             | `nifi-csv-consumer`    | Consumer group           |
| **Offset Reset**         | `earliest`             | Start from beginning     |
| **Message Demarcator**   | (empty)                | One message per flowfile |
| **Max Poll Records**     | `100`                  | Process one at a time    |
| **Max Uncommitted Time** | `1 min`                | Commit interval          |

### Scheduling

| Setting                 | Value        |
| ----------------------- | ------------ |
| **Scheduling Strategy** | Timer Driven |
| **Run Schedule**        | 1 sec        |
| **Concurrent Tasks**    | 1            |

### Settings

- **Auto Terminate Relationships:** (none)
- **Bulletin Level:** WARN

### Start Processor

Right-click → **Start**

---

## Processor 2: EvaluateJsonPath

### Add Processor

1. Drag **Processor** icon
2. Filter: `EvaluateJsonPath`
3. Click **Add**

### Configure Properties

| Property         | Value                | Description           |
| ---------------- | -------------------- | --------------------- |
| **Destination**  | `flowfile-attribute` | Extract to attributes |
| **Return Type**  | `json`               | JSON output           |
| **api_endpoint** | `$.api_endpoint`     | Download URL          |
| **upload_id**    | `$.upload_id`        | Upload ID             |
| **dataset_name** | `$.dataset_name`     | Dataset name          |
| **chunk_id**     | `$.chunk_id`         | Chunk number          |

**Add Custom Properties:**

Click **+** button for each property above.

### Settings

- **Auto Terminate Relationships:**
  - ✅ `unmatched`
  - ✅ `failure`

### Connect from ConsumeKafka

1. Hover over **ConsumeKafka** processor
2. Drag connection arrow to **EvaluateJsonPath**
3. Select relationship: `success`
4. Click **Add**

---

## Processor 3: InvokeHTTP

### Add Processor

1. Drag **Processor** icon
2. Filter: `InvokeHTTP`
3. Click **Add**

### Configure Properties

| Property                   | Value             | Description         |
| -------------------------- | ----------------- | ------------------- |
| **HTTP Method**            | `GET`             | Download file       |
| **Remote URL**             | `${api_endpoint}` | From Kafka message  |
| **Connection Timeout**     | `30 sec`          | Wait for connection |
| **Read Timeout**           | `60 sec`          | Wait for data       |
| **Follow Redirects**       | `true`            | Handle redirects    |
| **Always Output Response** | `false`           | Only success        |
| **Send Message Body**      | `false`           | No body for GET     |

### Scheduling

| Setting              | Value |
| -------------------- | ----- |
| **Concurrent Tasks** | 3     |
| **Run Schedule**     | 0 sec |

### Settings

- **Auto Terminate Relationships:**
  - ✅ `retry`
  - ✅ `failure`
  - ✅ `no retry`
  - ✅ `original`

### Connect from EvaluateJsonPath

1. Drag connection from **EvaluateJsonPath** to **InvokeHTTP**
2. Select: `matched`
3. Click **Add**

---

## Processor 4: ConvertRecord

### Add Processor

1. Drag **Processor** icon
2. Filter: `ConvertRecord`
3. Click **Add**

### Configure Controller Services

**IMPORTANT:** Create controller services first!

#### Create CSVReader

1. Click **Configuration** (gear icon in top-right)
2. Go to **Controller Services** tab
3. Click **+** button
4. Filter: `CSVReader`
5. Click **Add**
6. Click **⚙️** (Configure)

**CSVReader Properties:**

| Property                       | Value                 |
| ------------------------------ | --------------------- |
| **Schema Access Strategy**     | `Infer Schema`        |
| **Treat First Line as Header** | `true`                |
| **CSV Format**                 | `Custom Format`       |
| **Value Separator**            | `,`                   |
| **Skip Header Line**           | `false`               |
| **Ignore CSV Header**          | `false`               |
| **Date Format**                | `yyyy-MM-dd`          |
| **Time Format**                | `HH:mm:ss`            |
| **Timestamp Format**           | `yyyy-MM-dd HH:mm:ss` |

Click **Apply** → Click **⚡** (Enable)

#### Create ParquetRecordSetWriter

1. Still in Controller Services tab
2. Click **+** button
3. Filter: `ParquetRecordSetWriter`
4. Click **Add**
5. Click **⚙️** (Configure)

**ParquetRecordSetWriter Properties:**

| Property                   | Value                   |
| -------------------------- | ----------------------- |
| **Schema Write Strategy**  | `Embed Avro Schema`     |
| **Schema Access Strategy** | `Inherit Record Schema` |
| **Compression Type**       | `SNAPPY`                |
| **Enable Validation**      | `false`                 |

Click **Apply** → Click **⚡** (Enable)

### Configure ConvertRecord Processor

| Property                          | Value                                           |
| --------------------------------- | ----------------------------------------------- |
| **Record Reader**                 | `CSVReader` (select from dropdown)              |
| **Record Writer**                 | `ParquetRecordSetWriter` (select from dropdown) |
| **Include Zero Record FlowFiles** | `false`                                         |

### Settings

- **Auto Terminate Relationships:**
  - ✅ `failure`

### Connect from InvokeHTTP

1. Drag connection from **InvokeHTTP** to **ConvertRecord**
2. Select: `Response`
3. Click **Add**

---

## Processor 5: UpdateAttribute

### Add Processor

1. Drag **Processor** icon
2. Filter: `UpdateAttribute`
3. Click **Add**

### Configure Properties

Click **+** to add these custom properties:

| Property      | Value                                                              | Description       |
| ------------- | ------------------------------------------------------------------ | ----------------- |
| **s3.bucket** | `raw`                                                              | MinIO bucket name |
| **s3.key**    | `${dataset_name}/upload_id=${upload_id}/chunk_${chunk_id}.parquet` | S3 object path    |
| **filename**  | `chunk_${chunk_id}.parquet`                                        | File name         |

### Settings

- **Auto Terminate Relationships:** (none)

### Connect from ConvertRecord

1. Drag connection from **ConvertRecord** to **UpdateAttribute**
2. Select: `success`
3. Click **Add**

---

## Processor 6: PutS3Object

### Add Processor

1. Drag **Processor** icon
2. Filter: `PutS3Object`
3. Click **Add**

### Configure Properties

| Property                   | Value               | Description          |
| -------------------------- | ------------------- | -------------------- |
| **Bucket**                 | `${s3.bucket}`      | From UpdateAttribute |
| **Object Key**             | `${s3.key}`         | S3 path              |
| **Region**                 | `us-east-1`         | Required (any value) |
| **Access Key ID**          | `admin`             | MinIO access key     |
| **Secret Access Key**      | `admin123`          | MinIO secret key     |
| **Endpoint Override URL**  | `http://minio:9000` | MinIO service        |
| **Signer Override**        | `AWSS3V4SignerType` | S3v4 signing         |
| **Communications Timeout** | `30 sec`            | Upload timeout       |
| **Storage Class**          | `Standard`          | Default storage      |
| **Server Side Encryption** | `None`              | No encryption        |
| **Use Chunked Encoding**   | `false`             | Disable chunking     |

**IMPORTANT:** Use `http://minio:9000` (not localhost) - internal Kubernetes service name.

### Scheduling

| Setting              | Value |
| -------------------- | ----- |
| **Concurrent Tasks** | 3     |

### Settings

- **Auto Terminate Relationships:**
  - ✅ `success`
  - ✅ `failure`

### Connect from UpdateAttribute

1. Drag connection from **UpdateAttribute** to **PutS3Object**
2. Select: (default - no selection needed)
3. Click **Add**

---

## Final Flow Validation

### Check All Connections

Ensure all processors are connected:

```
ConsumeKafka (success) → EvaluateJsonPath
EvaluateJsonPath (matched) → InvokeHTTP
InvokeHTTP (Response) → ConvertRecord
ConvertRecord (success) → UpdateAttribute
UpdateAttribute → PutS3Object
```

### Check Controller Services

Both should be **ENABLED**:

- ✅ CSVReader
- ✅ ParquetRecordSetWriter

### Start All Processors

1. Select all processors (Ctrl+A)
2. Right-click → **Start**

Or start individually in order:

1. ConsumeKafka
2. EvaluateJsonPath
3. InvokeHTTP
4. ConvertRecord
5. UpdateAttribute
6. PutS3Object

---

## Testing

### 1. Upload CSV to Source API

```bash
# Port-forward Source API
kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000 &

# Upload test file
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi_test" \
  -F "chunk_type=rows" \
  -F "chunk_rows=100" \
  | jq '.'
```

Expected response:

```json
{
  "upload_id": "abc-xyz-123",
  "dataset_name": "taxi_test",
  "total_chunks": 3,
  "status": "processing"
}
```

### 2. Monitor NiFi Flow

Watch NiFi UI:

- **ConsumeKafka**: Should show increased `FlowFiles Out`
- **InvokeHTTP**: Check for `200 OK` responses
- **ConvertRecord**: Should show `Records Processed`
- **PutS3Object**: Should show `FlowFiles Sent`

### 3. Verify Kafka Messages

```bash
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic csv-ingestion \
    --from-beginning \
    --max-messages 1
```

### 4. Verify MinIO Files

```bash
# List files
mc ls local/raw/taxi_test/

# Expected output:
# [upload_id=abc-xyz-123]/
```

```bash
# List parquet files
mc ls local/raw/taxi_test/upload_id=abc-xyz-123/

# Expected:
# chunk_1.parquet
# chunk_2.parquet
# chunk_3.parquet
```

### 5. Download and Verify Parquet

```bash
# Download one file
mc cp local/raw/taxi_test/upload_id=*/chunk_1.parquet ./test.parquet

# View schema (requires parquet-tools)
parquet-tools schema test.parquet

# View data
parquet-tools head test.parquet -n 10
```

---

## Troubleshooting

### Issue 1: ConsumeKafka No Messages

**Symptoms:** No flowfiles output from ConsumeKafka

**Check:**

```bash
# Verify Kafka topic
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-topics.sh --describe --bootstrap-server localhost:9092 --topic csv-ingestion

# Check consumer group
kubectl exec -it openhouse-kafka-0 -n default -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group nifi-csv-consumer --describe
```

**Fix:**

- Ensure topic exists
- Check `Offset Reset` = `earliest`
- Verify Kafka broker address: `openhouse-kafka:9092`

---

### Issue 2: InvokeHTTP Connection Failed

**Symptoms:** `failure` or `no retry` relationships triggered

**Check:**

```bash
# Test Source API endpoint
kubectl exec -it <nifi-pod> -- curl http://fastapi-csv-uploader:8000/api/v1/health
```

**Fix:**

- Verify Source API is running
- Check `api_endpoint` attribute value in flowfile
- Ensure Source API service name is correct

---

### Issue 3: ConvertRecord Schema Errors

**Symptoms:** `failure` relationship triggered, errors about schema

**Check NiFi Logs:**

```bash
kubectl logs <nifi-pod> -n default | grep ConvertRecord
```

**Fix:**

- Ensure CSVReader is **enabled**
- Check CSV has header row
- Verify `Treat First Line as Header = true`
- Try manually defining schema instead of infer

---

### Issue 4: PutS3Object Upload Failed

**Symptoms:** `failure` relationship, S3 errors in logs

**Check:**

```bash
# Test MinIO connectivity from NiFi pod
kubectl exec -it <nifi-pod> -- curl http://minio:9000/minio/health/live

# Verify bucket exists
mc ls local/raw/
```

**Fix:**

- Ensure MinIO is running
- Check credentials: `admin` / `admin123`
- Verify endpoint: `http://minio:9000` (not localhost)
- Ensure Signer Override = `AWSS3V4SignerType`

---

### Issue 5: Controller Services Won't Enable

**Symptoms:** Error enabling CSVReader or ParquetRecordSetWriter

**Check:**

- Go to Controller Services tab
- Look for error icon next to service
- Click to view error details

**Fix:**

- Ensure no conflicting properties
- Restart NiFi if needed
- Recreate controller service

---

## Performance Tuning

### Increase Throughput

For **InvokeHTTP**, **ConvertRecord**, **PutS3Object**:

```
Concurrent Tasks: 5
Run Schedule: 0 sec
```

### Reduce Back Pressure

On each connection:

```
Back Pressure Object Threshold: 10000
Back Pressure Data Size Threshold: 1 GB
```

### Monitor Queue Sizes

Watch for queues filling up - indicates bottleneck.

---

## Monitoring

### NiFi UI Statistics

Check each processor for:

- **In / Out**: Number of flowfiles
- **Read / Written**: Data volume
- **Tasks / Time**: Processing time
- **Bulletin**: Errors and warnings

### View Provenance

Right-click flowfile → **View Provenance**

Shows complete lineage from Kafka to MinIO.

### System Diagnostics

Top menu → **Summary** → **System Diagnostics**

Check:

- Heap usage
- Thread count
- FlowFile repository size

---

## Cleanup

### Stop Flow

1. Select all processors
2. Right-click → **Stop**

### Remove Flow

1. Select all processors and connections
2. Press **Delete**

### Delete MinIO Data

```bash
mc rm --recursive --force local/raw/taxi_test/
```

---

## Additional Resources

- [NiFi Documentation](https://nifi.apache.org/docs.html)
- [MinIO Documentation](https://min.io/docs/minio/kubernetes/upstream/)
- [Parquet Format](https://parquet.apache.org/docs/)
- Source API Docs: `infra/k8s/ingestion/SOURCE-API.md`
