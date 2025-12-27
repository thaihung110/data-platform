# Kafka Testing Guide

## Mục đích

Hướng dẫn tạo pod test để kiểm tra kết nối và consume message từ Kafka trong cùng namespace.

## Prerequisites

- Kafka đã được deploy với SASL_PLAINTEXT authentication
- Có topic `csv-ingestion` đã được tạo hoặc auto-create enabled

## Bước 1: Deploy Kafka Test Client Pod

```bash
# Apply the test client pod
kubectl apply -f debug/kafka-test-client.yaml

# Chờ pod running
kubectl wait --for=condition=ready pod/kafka-test-client --timeout=60s

# Kiểm tra status
kubectl get pod kafka-test-client
```

## Bước 2: Exec vào Pod

```bash
kubectl exec -it kafka-test-client -- bash
```

## Bước 3: Test Kafka Connection trong Pod

### 3.1. Kiểm tra kết nối đến Kafka broker

```bash
# Test DNS resolution
nslookup openhouse-kafka

# Test network connectivity
telnet openhouse-kafka 9092
# (Ctrl+C để thoát nếu kết nối thành công)
```

### 3.2. List tất cả topics

```bash
kafka-topics.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/client.properties \
  --list
```

**Nếu lỗi SASL**, tạo file config trước:

```bash
cat > /tmp/client.properties <<EOF
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";
EOF
```

Sau đó chạy lại lệnh list topics.

### 3.3. Describe topic csv-ingestion

```bash
kafka-topics.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/client.properties \
  --describe \
  --topic csv-ingestion
```

### 3.4. Consume messages từ topic

**Consume từ đầu topic:**

```bash
kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
  --consumer.config /tmp/client.properties \
  --topic csv-ingestion \
  --from-beginning
```

**Consume chỉ message mới (real-time):**

```bash
kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
  --consumer.config /tmp/client.properties \
  --topic csv-ingestion
```

**Consume với group ID:**

```bash
kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
  --consumer.config /tmp/client.properties \
  --topic csv-ingestion \
  --group test-consumer-group \
  --from-beginning
```

**Consume và hiển thị key + timestamp:**

```bash
kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
  --consumer.config /tmp/client.properties \
  --topic csv-ingestion \
  --from-beginning \
  --property print.key=true \
  --property print.timestamp=true \
  --property key.separator=" | "
```

### 3.5. Produce test message

```bash
# Tạo producer config
cat > /tmp/producer.properties <<EOF
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";
EOF

# Produce message test
echo '{"test": "message from test client"}' | kafka-console-producer.sh \
  --bootstrap-server openhouse-kafka:9092 \
  --producer.config /tmp/producer.properties \
  --topic csv-ingestion
```

### 3.6. Kiểm tra consumer groups

```bash
# List all consumer groups
kafka-consumer-groups.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/client.properties \
  --list

# Describe consumer group
kafka-consumer-groups.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/client.properties \
  --group test-consumer-group \
  --describe
```

## Bước 4: Cleanup

```bash
# Thoát khỏi pod
exit

# Xóa test pod
kubectl delete pod kafka-test-client
```

## Troubleshooting

### Lỗi: "Broker: Request not valid in current SASL state"

**Nguyên nhân:** Kafka broker chưa enable SASL hoặc credentials sai.

**Giải pháp:**

1. Kiểm tra Kafka listener có `protocol: SASL_PLAINTEXT`
2. Verify credentials trong `/tmp/client.properties`
3. Kiểm tra logs: `kubectl logs openhouse-kafka-controller-0 -n data-platform | grep -i sasl`

### Lỗi: "Topic does not exist"

**Giải pháp:**

```bash
# Tạo topic thủ công nếu auto-create disabled
kafka-topics.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/client.properties \
  --create \
  --topic csv-ingestion \
  --partitions 1 \
  --replication-factor 1
```

### Lỗi: Connection timeout

**Giải pháp:**

1. Kiểm tra Kafka service: `kubectl get svc | grep kafka`
2. Kiểm tra Kafka pod running: `kubectl get pod | grep kafka`
3. Test DNS: `nslookup openhouse-kafka` trong pod

## Quick Reference

```bash
# One-liner: Deploy và exec vào pod
kubectl apply -f debug/kafka-test-client.yaml && \
kubectl wait --for=condition=ready pod/kafka-test-client --timeout=60s && \
kubectl exec -it kafka-test-client -- bash

# One-liner: Setup SASL config và consume
kubectl exec -it kafka-test-client -- bash -c \
  'cat > /tmp/client.properties <<EOF
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";
EOF
kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
  --consumer.config /tmp/client.properties \
  --topic csv-ingestion \
  --from-beginning'
```

## Expected Output

Khi consume thành công, bạn sẽ thấy messages dạng:

```json
{"upload_id": "abc-123", "chunk_id": 1, "dataset_name": "my_dataset", ...}
```

Nếu chưa có message, output sẽ trống và consumer sẽ chờ message mới (Ctrl+C để thoát).
