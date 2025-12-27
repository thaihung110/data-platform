# Spark Jobs

PySpark applications for data processing and ETL jobs.

## Files

- `ingest_taxi_data.py` - NYC taxi trip data ingestion to Iceberg bronze table
- `Dockerfile` - Docker image definition
- `build-image.sh` - Script to build and push Docker image to Docker Hub

**Docker Image**: `hungvt0110/ingestion-job`

## NYC Taxi Data Ingestion

Reads CSV data, cleans/transforms it, and loads into Iceberg table in bronze warehouse on lakekeeper.

## Build and Push Docker Image to Docker Hub

### Prerequisites

1. **Docker installed** and running
2. **Docker Hub account** (username: `hungvt0110`)
3. **Logged in to Docker Hub:**
   ```bash
   docker login -u hungvt0110
   # Enter your Docker Hub password or access token when prompted
   ```

### Build and Push Image

#### Option 1: Using Default Settings (Recommended)

```bash
cd spark-jobs
./build-image.sh
```

This will:

- Build image as `hungvt0110/ingestion-job:latest`
- Push to Docker Hub automatically

#### Option 2: Custom Image Name and Tag

```bash
# Build with custom name and tag
IMAGE_NAME=my-spark-jobs IMAGE_TAG=v1.0.0 ./build-image.sh

# Build without pushing (for testing)
PUSH_TO_DOCKERHUB=false ./build-image.sh

# Use different Docker Hub username
DOCKERHUB_USERNAME=your-username ./build-image.sh
```

#### Option 3: Manual Build and Push

```bash
# Build image
docker build -t hungvt0110/ingestion-job:latest .

# Tag with specific version
docker tag hungvt0110/ingestion-job:latest hungvt0110/ingestion-job:v1.0.0

# Push to Docker Hub
docker push hungvt0110/ingestion-job:latest
docker push hungvt0110/ingestion-job:v1.0.0
```

### Verify Image

```bash
# Check local images
docker images | grep hungvt0110/ingestion-job

# Test run locally
docker run --rm hungvt0110/ingestion-job:latest ls -la /app
```

### Image Details

- **Base Image**: `apache/spark-py:3.5.0`
- **Python Code Location**: `/app/ingest_taxi_data.py`
- **Docker Hub Repository**: `https://hub.docker.com/r/hungvt0110/ingestion-job`

## Local Development

```bash
# Set environment variables
export SPARK_MINOR_VERSION=3.5
export ICEBERG_VERSION=1.4.3
export CATALOG_URL=http://openhouse-lakekeeper-catalog:8181
export CLIENT_ID=your-client-id
export CLIENT_SECRET=your-client-secret
export WAREHOUSE=s3://warehouse/bronze
export KEYCLOAK_TOKEN_ENDPOINT=https://openhouse.keycloak.test/realms/iceberg/protocol/openid-connect/token

# Run with spark-submit
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.apache.iceberg:iceberg-aws-bundle:1.4.3 \
  ingest_taxi_data.py \
  data/raw/yellow_tripdata_2020-04.csv \
  bronze \
  taxi_trips
```

## Kubernetes Deployment

### Step 1: Build and Push Image

```bash
cd spark-jobs
./build-image.sh
```

### Step 2: Update SparkApplication Manifest

Update the image in `infra/k8s/compute/applications/taxi-data-ingestion.yaml`:

```yaml
image: hungvt0110/ingestion-job:latest
```

Or use a specific version:

```yaml
image: hungvt0110/ingestion-job:v1.0.0
```

### Step 3: Create Secrets

```bash
kubectl create secret generic lakekeeper-credentials \
  --from-literal=client-id=your-client-id \
  --from-literal=client-secret=your-client-secret \
  --namespace=default

# Optional: S3 credentials if using S3 warehouse
kubectl create secret generic s3-credentials \
  --from-literal=access-key-id=your-access-key \
  --from-literal=secret-access-key=your-secret-key \
  --namespace=default
```

### Step 4: Deploy SparkApplication

```bash
kubectl apply -f ../infra/k8s/compute/applications/taxi-data-ingestion.yaml
```

### Step 5: Monitor Job

```bash
# Check status
kubectl get sparkapplication taxi-data-ingestion -n default

# View driver logs
kubectl logs -l spark-role=driver -n default

# View executor logs
kubectl logs -l spark-role=executor -n default

# Describe for detailed status
kubectl describe sparkapplication taxi-data-ingestion -n default
```

## Configuration

Environment variables used by the application:

- `SPARK_MINOR_VERSION` (default: 3.5) - Spark version
- `ICEBERG_VERSION` (default: 1.4.3) - Iceberg version
- `CATALOG_URL` - Lakekeeper catalog service URL
- `CLIENT_ID` / `CLIENT_SECRET` - OAuth2 credentials for lakekeeper
- `WAREHOUSE` - S3 warehouse path (e.g., `s3://warehouse/bronze`)
- `KEYCLOAK_TOKEN_ENDPOINT` - Keycloak OAuth2 token endpoint URL

## Output Schema

The Iceberg table contains the following columns:

- `vendor_id` (int) - Vendor ID
- `pickup_datetime` (timestamp) - Pickup timestamp
- `dropoff_datetime` (timestamp) - Dropoff timestamp
- `passenger_count` (int) - Number of passengers
- `trip_distance` (double) - Trip distance in miles
- `rate_code_id` (int) - Rate code ID
- `store_and_fwd_flag` (string) - Store and forward flag
- `pu_location_id` (int) - Pickup location ID
- `do_location_id` (int) - Dropoff location ID
- `payment_type` (int) - Payment type
- `fare_amount` (double) - Fare amount
- `extra` (double) - Extra charges
- `mta_tax` (double) - MTA tax
- `tip_amount` (double) - Tip amount
- `tolls_amount` (double) - Tolls amount
- `improvement_surcharge` (double) - Improvement surcharge
- `total_amount` (double) - Total amount
- `congestion_surcharge` (double) - Congestion surcharge
- `ingestion_timestamp` (timestamp) - When the record was ingested
- `data_source` (string) - Source file identifier

## Troubleshooting

### Docker Build Issues

**Build fails:**

- Check Docker is running: `docker ps`
- Verify Dockerfile syntax
- Check base image is accessible: `docker pull apache/spark-py:3.5.0`

**Push fails:**

- Verify login: `docker login -u hungvt0110`
- Check image name matches Docker Hub repository (`hungvt0110/ingestion-job`)
- Ensure repository exists on Docker Hub (create it if needed)

### Kubernetes Deployment Issues

**Image pull errors:**

- Verify image exists: `docker pull hungvt0110/ingestion-job:latest`
- Check imagePullPolicy in manifest
- Verify Kubernetes can access Docker Hub

**Job fails:**

- Check SparkApplication status: `kubectl describe sparkapplication taxi-data-ingestion`
- View logs: `kubectl logs -l spark-role=driver -n default`
- Verify secrets exist: `kubectl get secrets -n default`
