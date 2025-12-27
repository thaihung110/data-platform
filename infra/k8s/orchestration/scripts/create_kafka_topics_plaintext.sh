#!/bin/bash

# Script to create Kafka topics (PLAINTEXT - No SASL)
# Usage: ./create_kafka_topics_plaintext.sh

set -e

NAMESPACE="${NAMESPACE:-default}"
KAFKA_POD="openhouse-kafka-controller-0 "
TOPIC_NAME="${1:-csv-ingestion}"
PARTITIONS="${2:-1}"
REPLICATION_FACTOR="${3:-1}"

echo "=========================================="
echo "Creating Kafka Topic"
echo "=========================================="
echo "Topic Name: $TOPIC_NAME"
echo "Namespace: $NAMESPACE"
echo "Partitions: $PARTITIONS"
echo "Replication Factor: $REPLICATION_FACTOR"
echo "=========================================="
echo ""

# Create the topic using kafka-topics.sh from within the Kafka pod
echo "Creating topic..."
kubectl exec -n $NAMESPACE $KAFKA_POD -- kafka-topics.sh \
  --create \
  --topic $TOPIC_NAME \
  --partitions $PARTITIONS \
  --replication-factor $REPLICATION_FACTOR \
  --if-not-exists \
  --bootstrap-server localhost:9092

echo ""
echo "✅ Topic '$TOPIC_NAME' created successfully!"

# List all topics to verify
echo ""
echo "=========================================="
echo "Current Topics:"
echo "=========================================="
kubectl exec -n $NAMESPACE $KAFKA_POD -- kafka-topics.sh \
  --list \
  --bootstrap-server localhost:9092

echo ""
echo "=========================================="
echo "Topic Details:"
echo "=========================================="
kubectl exec -n $NAMESPACE $KAFKA_POD -- kafka-topics.sh \
  --describe \
  --topic $TOPIC_NAME \
  --bootstrap-server localhost:9092
