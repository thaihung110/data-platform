# NiFi Kafka Consumer Troubleshooting

## Vấn đề

NiFi processor **ConsumeKafka** không thể consume messages từ Kafka topic `csv-ingestion`, mặc dù test bằng `kafka-console-consumer` từ pod khác thành công.

## Root Cause Analysis

### ✅ Test Pod Configuration (Thành công)

```bash
# File: /tmp/kafka-consumer.properties
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";
```

**Kết quả:** Consume thành công 3 messages

### ❌ NiFi Processor Configuration (Thất bại)

```
Kafka Brokers: openhouse-kafka:9092
Topic Name(s): csv-ingestion
Security Protocol: PLAINTEXT          ← VẤN ĐỀ Ở ĐÂY!
SASL Mechanism: PLAIN
Username: admin
Password: admin
```

## Nguyên nhân

**Security Protocol mismatch:**

| Component          | Expected         | Configured       | Result                    |
| ------------------ | ---------------- | ---------------- | ------------------------- |
| Kafka Broker       | `SASL_PLAINTEXT` | `SASL_PLAINTEXT` | ✅                        |
| Test Pod           | `SASL_PLAINTEXT` | `SASL_PLAINTEXT` | ✅ Consume thành công     |
| **NiFi Processor** | `SASL_PLAINTEXT` | **`PLAINTEXT`**  | ❌ **Không consume được** |

### Giải thích chi tiết

1. **Kafka broker** đã được cấu hình với listener `SASL_PLAINTEXT` (port 9092)

   - Yêu cầu SASL authentication với mechanism PLAIN
   - Username/password: admin/admin

2. **NiFi processor đang dùng `PLAINTEXT`:**

   - Không gửi SASL credentials
   - Broker từ chối kết nối vì thiếu authentication
   - Không có error message rõ ràng trong NiFi UI (thường chỉ thấy "no messages")

3. **Khi set `SASL_PLAINTEXT`:**
   - NiFi sẽ gửi SASL handshake với username/password
   - Broker accept connection
   - Consumer có thể consume messages

## Giải pháp

### Bước 1: Cập nhật NiFi Processor Configuration

Trong NiFi UI, chỉnh sửa processor **ConsumeKafka**:

**BEFORE:**

```
Security Protocol: PLAINTEXT
```

**AFTER:**

```
Security Protocol: SASL_PLAINTEXT
```

### Bước 2: Verify các properties khác

Đảm bảo các properties sau đúng:

| Property              | Value                  | Note                      |
| --------------------- | ---------------------- | ------------------------- |
| Kafka Brokers         | `openhouse-kafka:9092` | Service name trong K8s    |
| Topic Name(s)         | `csv-ingestion`        | Topic name                |
| Topic Name Format     | `names`                | ✅                        |
| Group ID              | `nifi-csv-consumer`    | ✅ Bất kỳ tên gì cũng ok  |
| **Security Protocol** | **`SASL_PLAINTEXT`**   | ⚠️ PHẢI ĐỔI               |
| SASL Mechanism        | `PLAIN`                | ✅                        |
| Username              | `admin`                | ✅                        |
| Password              | `admin`                | ✅ (sensitive value)      |
| Offset Reset          | `earliest`             | ✅ Consume from beginning |
| Max Poll Records      | `100`                  | ✅                        |
| Commit Offsets        | `true`                 | ✅                        |

### Bước 3: Apply và Test

1. **Stop** processor (nếu đang chạy)
2. **Apply** configuration changes
3. **Start** processor
4. Monitor FlowFiles - should see messages flowing

## Verification Steps

### 1. Kiểm tra NiFi Logs

```bash
kubectl logs openhouse-nifi-0 -c nifi | grep -i kafka
```

**Nếu vẫn lỗi**, bạn sẽ thấy:

```
ERROR [ConsumeKafka] Failed to consume from Kafka
ERROR SASL authentication failed
```

**Nếu thành công**, bạn sẽ thấy:

```
INFO [ConsumeKafka] Successfully consumed X records from topic csv-ingestion
```

### 2. Kiểm tra Consumer Group trong Kafka

Exec vào test pod và kiểm tra consumer groups:

```bash
kubectl exec -it kafka-test-client -- bash

# List consumer groups
kafka-consumer-groups.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/kafka-consumer.properties \
  --list

# Should see: nifi-csv-consumer

# Describe NiFi consumer group
kafka-consumer-groups.sh --bootstrap-server openhouse-kafka:9092 \
  --command-config /tmp/kafka-consumer.properties \
  --group nifi-csv-consumer \
  --describe
```

**Expected output nếu NiFi đang consume:**

```
GROUP             TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
nifi-csv-consumer csv-ingestion   0          3               3               0
```

- **CURRENT-OFFSET = LOG-END-OFFSET:** Đã consume hết messages
- **LAG = 0:** Không có messages pending

### 3. Test End-to-End Flow

1. Upload CSV file qua source-api
2. Verify messages xuất hiện trong Kafka:
   ```bash
   kafka-console-consumer.sh --bootstrap-server openhouse-kafka:9092 \
     --consumer.config /tmp/kafka-consumer.properties \
     --topic csv-ingestion --from-beginning
   ```
3. Verify NiFi processor nhận được FlowFiles
4. Check downstream processors xử lý FlowFiles

## Common Pitfalls

### ❌ Group ID không phải vấn đề

Group ID chỉ để:

- Identify consumer group (cho coordination)
- Track offset consumption
- Tên bất kỳ đều OK, không ảnh hưởng đến authentication

### ❌ Password field trống

Nếu password field hiển thị "Sensitive value set", điều đó **OK**.
Chỉ cần đảm bảo password đã được set = `admin` lần đầu.

### ❌ Max Poll Records quá thấp

Nếu set = 1, processor sẽ chỉ consume 1 message/lần poll.
Recommend: 100-1000 cho performance tốt hơn.

## Additional NiFi Kafka Properties

Nếu muốn tune performance, có thể thêm các properties sau trong **Additional Configuration**:

```properties
# Session timeout (default 10s)
session.timeout.ms=30000

# Max poll interval (default 5min)
max.poll.interval.ms=300000

# Heartbeat interval (default 3s)
heartbeat.interval.ms=10000

# Fetch min bytes (default 1)
fetch.min.bytes=1024

# Fetch max wait (default 500ms)
fetch.max.wait.ms=1000
```

## Reference Architecture

```
┌─────────────────┐
│  Source API     │
│  (Producer)     │
└────────┬────────┘
         │ Produce messages
         │ (SASL_PLAINTEXT)
         ▼
┌─────────────────────────────┐
│   Kafka Broker              │
│   openhouse-kafka:9092      │
│   Listener: SASL_PLAINTEXT  │
│   Credentials: admin/admin  │
└────────┬────────────────────┘
         │ Consume messages
         │ (SASL_PLAINTEXT)
         ▼
┌─────────────────┐
│  NiFi Processor │
│  ConsumeKafka   │
│  Group: nifi-   │
│  csv-consumer   │
└─────────────────┘
```

## Quick Fix Checklist

- [ ] NiFi processor stopped
- [ ] Security Protocol changed to `SASL_PLAINTEXT`
- [ ] Username = `admin`
- [ ] Password = `admin` (sensitive value set)
- [ ] Processor restarted
- [ ] Check for FlowFiles in queue
- [ ] Verify consumer group offset in Kafka

## Summary

**Vấn đề:** Security Protocol = `PLAINTEXT` không match với Kafka broker's `SASL_PLAINTEXT`.

**Giải pháp:** Đổi sang `SASL_PLAINTEXT` trong NiFi processor configuration.

**Verification:** Check consumer group offsets và NiFi processor stats.
