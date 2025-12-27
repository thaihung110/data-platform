#!/bin/bash

# Script to create ConfigMap containing Spark job manifests for Airflow DAGs
# This ConfigMap will be mounted into Airflow pods to access SparkApplication YAML files

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
MANIFEST_DIR="$( cd "${SCRIPT_DIR}/../applications/spark/legacy" && pwd )"
NAMESPACE="default"

echo "=========================================="
echo "Creating Spark Manifests ConfigMap"
echo "=========================================="
echo "Namespace: ${NAMESPACE}"
echo "Manifest Directory: ${MANIFEST_DIR}"
echo "=========================================="
echo ""

# Create ConfigMap from the taxi-data-ingestion.yaml file
kubectl create configmap spark-manifests \
    --from-file=taxi-data-ingestion.yaml="${MANIFEST_DIR}/taxi-data-ingestion.yaml" \
    -n "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "✅ ConfigMap 'spark-manifests' created/updated successfully!"
echo ""
echo "📋 Verify ConfigMap:"
echo "   kubectl get configmap spark-manifests -n ${NAMESPACE}"
echo ""
echo "📋 View ConfigMap contents:"
echo "   kubectl describe configmap spark-manifests -n ${NAMESPACE}"
echo "=========================================="
