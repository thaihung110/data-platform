# Airflow DAG - Taxi Data Ingestion

## Overview

This DAG orchestrates the taxi data ingestion Spark job that reads Parquet files from MinIO's raw bucket and loads them into Lakekeeper's Iceberg bronze table.

## DAG Configuration

- **DAG ID**: `taxi-data-ingestion-spark`
- **Schedule**: Hourly (`@hourly`)
- **Owner**: data-engineering
- **Tags**: `data-ingestion`, `spark`, `taxi`, `bronze`
- **Max Active Runs**: 1 (prevents concurrent executions)

## Tasks

### 1. `submit_taxi_ingestion_spark_job`

- **Type**: KubernetesPodOperator
- **Purpose**: Applies the SparkApplication manifest to Kubernetes
- **Image**: `bitnami/kubectl:latest`
- **Command**: `kubectl apply -f /mnt/manifests/taxi-data-ingestion.yaml`

### 2. `monitor_taxi_ingestion_spark_job`

- **Type**: SparkKubernetesSensor
- **Purpose**: Monitors the SparkApplication until completion
- **Poke Interval**: 30 seconds
- **Timeout**: 1 hour

### 3. `cleanup_taxi_ingestion_spark_job`

- **Type**: KubernetesPodOperator
- **Purpose**: Deletes the SparkApplication after completion
- **Trigger Rule**: `all_done` (runs even if previous tasks fail)

## Prerequisites

### 1. Create ConfigMap for Spark Manifests

The DAG requires a ConfigMap containing the SparkApplication YAML file:

```bash
cd infra/k8s/compute/scripts
chmod +x create_spark_manifests_configmap.sh
./create_spark_manifests_configmap.sh
```

This creates a ConfigMap named `spark-manifests` in the `default` namespace.

### 2. Verify Airflow Service Account Permissions

Ensure the Airflow service account has permissions to:

- Create/delete SparkApplications
- Create/monitor pods
- Access ConfigMaps

The DAG uses `openhouse-spark-operator-spark` service account.

### 3. Deploy DAG to Airflow

Copy the DAG file to Airflow's DAGs folder:

```bash
# If using volume mount
cp airflow/dags/taxi_data_ingestion_dag.py /path/to/airflow/dags/

# Or if using git-sync, commit and push
git add airflow/dags/taxi_data_ingestion_dag.py
git commit -m "Add taxi data ingestion DAG"
git push
```

## Deployment Steps

### Step 1: Create ConfigMap

```bash
cd infra/k8s/compute/scripts
./create_spark_manifests_configmap.sh
```

### Step 2: Verify ConfigMap

```bash
kubectl get configmap spark-manifests -n default
kubectl describe configmap spark-manifests -n default
```

### Step 3: Access Airflow UI

```bash
# Port forward to access Airflow UI
kubectl port-forward svc/openhouse-airflow-api-server 8080:8080 -n default
```

Open browser: http://localhost:8080

### Step 4: Enable DAG

1. Navigate to DAGs page
2. Find `taxi-data-ingestion-spark`
3. Toggle the DAG to **ON**

### Step 5: Trigger Manual Run (Optional)

Click the "Play" button to trigger a manual run for testing.

## Monitoring

### View DAG Execution

1. **Airflow UI**: Navigate to DAGs → `taxi-data-ingestion-spark` → Graph View
2. **Task Logs**: Click on any task to view logs

### Monitor Spark Job

```bash
# View SparkApplication status
kubectl get sparkapplication taxi-data-ingestion -n default

# View driver logs
kubectl logs -l spark-role=driver,spark-app-name=taxi-data-ingestion -n default -f

# View executor logs
kubectl logs -l spark-role=executor,spark-app-name=taxi-data-ingestion -n default -f
```

### Verify Data in Iceberg

After successful execution, verify data was loaded:

```sql
-- From Spark SQL or Trino
SELECT COUNT(*) FROM lakekeeper.bronze.taxi_trips;
SELECT * FROM lakekeeper.bronze.taxi_trips LIMIT 10;
```

## Troubleshooting

### DAG Not Appearing in Airflow UI

1. Check DAG file syntax:

   ```bash
   python airflow/dags/taxi_data_ingestion_dag.py
   ```

2. Check Airflow scheduler logs:
   ```bash
   kubectl logs -l component=scheduler -n default -f
   ```

### ConfigMap Not Found Error

Ensure ConfigMap is created:

```bash
kubectl get configmap spark-manifests -n default
```

If missing, run the creation script again.

### Permission Denied Errors

Check service account permissions:

```bash
kubectl describe serviceaccount openhouse-spark-operator-spark -n default
```

### Spark Job Fails

1. Check SparkApplication status:

   ```bash
   kubectl describe sparkapplication taxi-data-ingestion -n default
   ```

2. Check driver pod logs:
   ```bash
   kubectl logs -l spark-role=driver,spark-app-name=taxi-data-ingestion -n default
   ```

## Schedule Modification

To change the schedule, edit `taxi_data_ingestion_dag.py`:

```python
schedule_interval="@hourly",  # Current: every hour

# Examples:
# schedule_interval="@daily",      # Once per day at midnight
# schedule_interval="0 */6 * * *", # Every 6 hours
# schedule_interval=None,          # Manual trigger only
```

## Notes

- The DAG prevents concurrent runs (`max_active_runs=1`)
- Failed tasks will retry 2 times with 5-minute delay
- SparkApplication is automatically cleaned up after completion
- Job reads from: `s3a://raw/taxi/*/*.parquet`
- Job writes to: `lakekeeper.bronze.taxi_trips`
