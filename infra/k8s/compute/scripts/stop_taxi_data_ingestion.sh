#!/bin/bash

# Script to stop/delete the taxi-data-ingestion SparkApplication

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
NAMESPACE="default"
JOB_NAME="taxi-data-ingestion"

echo "=========================================="
echo "Stopping Taxi Data Ingestion Spark Job"
echo "=========================================="
echo "Job Name: ${JOB_NAME}"
echo "Namespace: ${NAMESPACE}"
echo "=========================================="
echo ""

# Check if job exists
if ! kubectl get sparkapplication "${JOB_NAME}" -n "${NAMESPACE}" &>/dev/null; then
    echo "ℹ️  SparkApplication '${JOB_NAME}' not found in namespace '${NAMESPACE}'"
    echo "   It may have already been deleted or never created."
    exit 0
fi

# Show current status
echo "📊 Current status:"
kubectl get sparkapplication "${JOB_NAME}" -n "${NAMESPACE}"
echo ""

# Get job state
STATE=$(kubectl get sparkapplication "${JOB_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.applicationState.state}' 2>/dev/null || echo "UNKNOWN")

if [ "${STATE}" = "RUNNING" ] || [ "${STATE}" = "SUBMITTED" ]; then
    echo "⚠️  Job is currently ${STATE}"
    echo "   Deleting will stop the running job..."
    echo ""
    read -p "Are you sure you want to stop this job? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted."
        exit 0
    fi
fi

# Delete SparkApplication
echo "🗑️  Deleting SparkApplication '${JOB_NAME}'..."
kubectl delete sparkapplication "${JOB_NAME}" -n "${NAMESPACE}" --wait=true

# Wait for pods to terminate
echo ""
echo "⏳ Waiting for Spark pods to terminate..."
sleep 5

# Check for remaining pods
DRIVER_PODS=$(kubectl get pods -n "${NAMESPACE}" -l spark-role=driver,spark-app-name="${JOB_NAME}" --no-headers 2>/dev/null | wc -l)
EXECUTOR_PODS=$(kubectl get pods -n "${NAMESPACE}" -l spark-role=executor,spark-app-name="${JOB_NAME}" --no-headers 2>/dev/null | wc -l)

if [ "${DRIVER_PODS}" -gt 0 ] || [ "${EXECUTOR_PODS}" -gt 0 ]; then
    echo "⚠️  Some Spark pods are still running:"
    kubectl get pods -n "${NAMESPACE}" -l spark-app-name="${JOB_NAME}"
    echo ""
    echo "💡 They will be cleaned up automatically by Spark Operator."
    echo "   You can force delete them if needed:"
    echo "   kubectl delete pods -n ${NAMESPACE} -l spark-app-name=${JOB_NAME}"
else
    echo "✅ All Spark pods have been terminated"
fi

echo ""
echo "=========================================="
echo "✅ SparkApplication stopped successfully!"
echo "=========================================="
echo ""
echo "📋 To start again:"
echo "   ${SCRIPT_DIR}/start_taxi_data_ingestion.sh"
echo "=========================================="

