# Hướng Dẫn Cấu Hình Airflow cho CSV Ingestion Listener

## Tổng Quan

DAG `csv-ingestion-listener` lắng nghe Kafka topic `csv-ingestion` và trigger NiFi process group để xử lý CSV chunks được upload lên source-api.

## Yêu Cầu

1. Airflow đã được deploy lên Kubernetes
2. Airflow provider packages:
   - `apache-airflow-providers-apache-kafka`
   - `apache-airflow-providers-http`
3. Kafka cluster đang chạy với SASL authentication
4. NiFi cluster đang chạy

---

## Bước 1: Tạo Airflow Connections

### 1.1. Kafka Connection

**Truy cập Airflow UI:**

1. Đăng nhập vào Airflow web UI
2. Vào **Admin** → **Connections**
3. Click **+** (Add a new record)

**Cấu hình:**

| Field           | Value                 |
| --------------- | --------------------- |
| Connection Id   | `kafka_csv_ingestion` |
| Connection Type | `Kafka`               |
| Host            | `openhouse-kafka`     |
| Port            | `9092`                |
| Extra           | (Xem JSON bên dưới)   |

**Extra JSON:**

```json
{
  "bootstrap.servers": "openhouse-kafka:9092",
  "security.protocol": "SASL_PLAINTEXT",
  "sasl.mechanism": "PLAIN",
  "sasl.username": "admin",
  "sasl.password": "admin",
  "group.id": "airflow-csv-ingestion-consumer",
  "auto.offset.reset": "latest",
  "enable.auto.commit": true,
  "session.timeout.ms": 30000
}
```

**Giải thích:**

- `bootstrap.servers`: Địa chỉ Kafka broker trong cluster
- `security.protocol`: SASL_PLAINTEXT (SASL auth không dùng TLS)
- `sasl.mechanism`: PLAIN (username/password authentication)
- `sasl.username/password`: Credentials để connect vào Kafka
- `group.id`: Consumer group ID để track offset
- `auto.offset.reset`: `latest` - chỉ consume messages mới, không process messages cũ

---

### 1.2. NiFi HTTP Connection

**Cấu hình:**

| Field           | Value                    |
| --------------- | ------------------------ |
| Connection Id   | `nifi_rest_api`          |
| Connection Type | `HTTP`                   |
| Host            | `https://openhouse-nifi` |
| Port            | `8443`                   |
| Extra           | (Xem JSON bên dưới)      |

**Extra JSON (Option 1: No Authentication):**

```json
{
  "verify": false
}
```

**Extra JSON (Option 2: With Basic Auth):**

```json
{
  "verify": false,
  "auth": ["nifi_username", "nifi_password"]
}
```

**Extra JSON (Option 3: With Token Auth):**

```json
{
  "verify": false,
  "headers": {
    "Authorization": "Bearer YOUR_NIFI_TOKEN"
  }
}
```

> **Lưu ý:**
>
> - `verify: false` để bỏ qua SSL certificate validation (chỉ dùng trong dev/test)
> - Trong production, nên set `verify: true` và cung cấp CA certificate

---

## Bước 2: Tạo Airflow Variable

**Truy cập Airflow UI:**

1. Vào **Admin** → **Variables**
2. Click **+** (Add a new record)

**Cấu hình:**

| Key                     | Value                                  |
| ----------------------- | -------------------------------------- |
| `nifi_process_group_id` | `4be3c5be-019b-1000-4ef1-949cbb8c08de` |

**Giải thích:**

- Biến này lưu ID của NiFi process group cần trigger
- DAG sẽ đọc giá trị này khi cần trigger NiFi

---

## Bước 3: Test Connections

### 3.1. Test Kafka Connection

**Từ Airflow Scheduler Pod:**

```bash
# Exec vào scheduler pod
kubectl exec -it <airflow-scheduler-pod-name> -- bash

# Test connection
airflow connections test kafka_csv_ingestion
```

**Expected Output:**

```
Connection successfully tested
```

**Nếu gặp lỗi:**

- Verify Kafka service đang chạy: `kubectl get svc | grep kafka`
- Check SASL credentials trong connection Extra
- Verify network policy cho phép Airflow connect tới Kafka

---

### 3.2. Test NiFi Connection

**Từ Airflow Scheduler Pod:**

```bash
# Test connection
airflow connections test nifi_rest_api

# Hoặc test bằng curl
curl -k https://openhouse-nifi:8443/nifi-api/system-diagnostics
```

**Expected Output:**

```
Connection successfully tested
```

Hoặc JSON response từ NiFi API

**Nếu gặp lỗi:**

- Verify NiFi service: `kubectl get svc | grep nifi`
- Check NiFi authentication nếu có bật
- Verify network policy

---

### 3.3. Test Kafka Message Consumption

**Từ Kafka Pod:**

```bash
# Exec vào Kafka pod
kubectl exec -it openhouse-kafka-0 -- bash

# Consume messages từ topic
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic csv-ingestion \
  --from-beginning \
  --consumer-property security.protocol=SASL_PLAINTEXT \
  --consumer-property sasl.mechanism=PLAIN \
  --consumer-property sasl.jaas.config='org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="admin";'
```

**Kiểm tra:**

- Có messages hiển thị không?
- Message format có đúng như expected không?

---

## Bước 4: Deploy & Enable DAG

### 4.1. Copy DAG File

**Nếu dùng Git-Sync:**

```bash
# DAG file đã ở trong: airflow/dags/csv_ingestion_listener_dag.py
# Git-sync sẽ tự động sync từ git repo
```

**Nếu dùng PVC mount:**

```bash
# Copy file vào Airflow DAGs folder
kubectl cp airflow/dags/csv_ingestion_listener_dag.py \
  <airflow-scheduler-pod>:/opt/airflow/dags/
```

### 4.2. Verify DAG Appears

**Từ Airflow UI:**

1. Vào **DAGs** page
2. Tìm DAG: `csv-ingestion-listener`
3. Verify DAG không có errors

**Hoặc từ CLI:**

```bash
kubectl exec -it <airflow-scheduler-pod> -- \
  airflow dags list | grep csv-ingestion-listener
```

### 4.3. Test DAG Syntax

```bash
kubectl exec -it <airflow-scheduler-pod> -- bash

# Test DAG import
python /opt/airflow/dags/csv_ingestion_listener_dag.py

# List tasks trong DAG
airflow dags show csv-ingestion-listener

# Test specific task
airflow tasks test csv-ingestion-listener listen_kafka_csv_topic 2025-12-26
```

---

## Bước 5: End-to-End Testing

### 5.1. Upload CSV File

```bash
# Upload CSV file qua source-api
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -F "file=@taxi.csv" \
  -F "dataset_name=taxi_test" \
  -F "chunk_type=rows" \
  -F "chunk_rows=100"
```

**Expected:**

- Source-api sẽ publish messages tới Kafka topic `csv-ingestion`
- Mỗi chunk sẽ là 1 message

### 5.2. Monitor Airflow DAG

**Trong Airflow UI:**

1. DAG `csv-ingestion-listener` sẽ tự động trigger (nếu enabled)
2. Theo dõi task execution:
   - `listen_kafka_csv_topic` - Đang lắng nghe Kafka
   - `extract_message_data` - Extract message
   - `trigger_nifi_process_group` - Trigger NiFi

**Xem Logs:**

- Click vào mỗi task → **Log**
- Verify message được nhận và validate đúng
- Check NiFi trigger response

### 5.3. Verify NiFi Processing

**Trong NiFi UI:**

1. Truy cập process group: `4be3c5be-019b-1000-4ef1-949cbb8c08de`
2. Verify processors đang chạy (state: RUNNING)
3. Check data flow qua các processors
4. Verify output (files trong MinIO, data trong database, etc.)

---

## Troubleshooting

### Issue 1: DAG Không Trigger

**Triệu chứng:**

- DAG appears trong UI nhưng không trigger khi có message

**Giải quyết:**

1. Enable DAG trong UI (toggle switch)
2. Check DAG schedule: `schedule_interval=None` là event-driven
3. Manually trigger: Click **▶ Trigger DAG**
4. Check Airflow scheduler logs:
   ```bash
   kubectl logs <airflow-scheduler-pod> | grep csv-ingestion
   ```

---

### Issue 2: Kafka Connection Failed

**Triệu chứng:**

```
Connection refused / Authentication failed
```

**Giải quyết:**

1. Verify Kafka service DNS:

   ```bash
   kubectl get svc openhouse-kafka
   nslookup openhouse-kafka
   ```

2. Test network connectivity:

   ```bash
   kubectl exec -it <airflow-scheduler-pod> -- \
     nc -zv openhouse-kafka 9092
   ```

3. Verify SASL credentials:

   ```bash
   # Get Kafka SASL password from secret
   kubectl get secret <kafka-secret-name> -o jsonpath='{.data.client-passwords}' | base64 -d
   ```

4. Check Kafka listener configuration:
   ```bash
   kubectl exec -it openhouse-kafka-0 -- \
     cat /opt/bitnami/kafka/config/server.properties | grep listener
   ```

---

### Issue 3: NiFi Trigger Failed

**Triệu chứng:**

```
Failed to trigger NiFi PG. Status: 401/403/404
```

**Giải quyết:**

**Status 401/403 (Unauthorized/Forbidden):**

- NiFi requires authentication
- Update connection với username/password hoặc token
- Check NiFi user permissions

**Status 404 (Not Found):**

- Process group ID không tồn tại
- Verify ID trong NiFi UI:
  1. Right-click process group → Configure
  2. Check ID trong Settings tab
- Update Airflow Variable `nifi_process_group_id`

**Status 500 (Internal Server Error):**

- Check NiFi logs:
  ```bash
  kubectl logs <nifi-pod> | grep ERROR
  ```

---

### Issue 4: Message Format Invalid

**Triệu chứng:**

```
Invalid message - missing fields: [...]
```

**Giải quyết:**

1. Check message format từ source-api
2. Verify required fields trong DAG code
3. Update `listen_for_csv_messages` function nếu cần

---

## Monitoring & Maintenance

### Monitor DAG Execution

**Airflow Metrics:**

- DAG run success rate
- Task duration
- Failed tasks count

**Kafka Metrics:**

- Consumer lag: Số messages chưa được consume
- Message processing rate

```bash
# Check consumer group lag
kubectl exec -it openhouse-kafka-0 -- \
  kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --describe \
    --group airflow-csv-ingestion-consumer \
    --command-config /opt/bitnami/kafka/config/consumer.properties
```

### Log Locations

**Airflow Logs:**

- Scheduler: `kubectl logs <airflow-scheduler-pod>`
- Task logs: Airflow UI → DAG → Task → Log

**Kafka Logs:**

- `kubectl logs <kafka-pod>`

**NiFi Logs:**

- `kubectl logs <nifi-pod>`
- NiFi UI → Summary → View System Diagnostics → Logs

---

## Advanced Configuration

### Parallel Message Processing

DAG configuration cho phép xử lý nhiều messages đồng thời:

```python
max_active_runs=5  # Cho phép 5 DAG runs cùng lúc
```

**Lưu ý:**

- Tăng `max_active_runs` nếu có nhiều CSV uploads đồng thời
- Monitor Airflow worker resources (CPU, memory)

### Custom Consumer Group

Thay đổi `group.id` trong Kafka connection nếu muốn:

- Reset offset và consume lại từ đầu
- Tạo multiple consumers cho cùng topic

### Retry Strategy

DAG configuration:

```python
"retries": 3,
"retry_delay": timedelta(minutes=2),
```

Điều chỉnh tùy theo:

- Network reliability
- NiFi availability
- Business requirements

---

## Security Best Practices

### 1. Kafka Authentication

✅ **Đang làm:**

- SASL_PLAINTEXT with username/password

⚠️ **Nên cải thiện:**

- Sử dụng SASL_SSL thay vì SASL_PLAINTEXT (encrypt credentials)
- Rotate passwords định kỳ
- Sử dụng SCRAM-SHA-256/512 thay vì PLAIN

### 2. NiFi Authentication

⚠️ **Hiện tại:**

- `verify: false` - bỏ qua SSL verification

✅ **Production:**

- Enable SSL verification
- Sử dụng certificates
- Enable NiFi authentication (username/password hoặc certificates)

### 3. Airflow Connections

✅ **Best practice:**

- Lưu sensitive data trong Airflow Connections (encrypted)
- KHÔNG hardcode credentials trong DAG code
- Sử dụng Kubernetes Secrets cho connections

---

## FAQ

**Q: DAG có thể miss messages không?**

A: Không, nhờ Kafka consumer group và offset tracking:

- Kafka lưu offset của mỗi message đã consume
- Nếu Airflow restart, sẽ tiếp tục từ offset cuối cùng
- `auto.offset.reset: latest` chỉ áp dụng cho first-time connection

**Q: DAG có xử lý messages theo thứ tự không?**

A: Không đảm bảo thứ tự nếu `max_active_runs > 1`:

- Nhiều DAG runs có thể chạy parallel
- Để đảm bảo thứ tự, set `max_active_runs=1`

**Q: Làm sao để replay/reprocess messages?**

A: Reset consumer group offset:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server openhouse-kafka:9092 \
  --group airflow-csv-ingestion-consumer \
  --reset-offsets \
  --to-earliest \
  --topic csv-ingestion \
  --execute
```

**Q: NiFi process group đã chạy rồi, trigger lại có sao không?**

A: Tùy thuộc NiFi configuration:

- Nếu processors đang RUNNING, request có thể ignored hoặc restart
- Best practice: Check state trước khi trigger

---

## Next Steps

1. ✅ Cấu hình connections và variables
2. ✅ Deploy và test DAG
3. 📝 Setup monitoring & alerting
4. 📝 Configure backups cho Airflow metadata
5. 📝 Implement data quality checks
6. 📝 Add metrics dashboard (Grafana)

---

## References

- [Airflow Kafka Provider Documentation](https://airflow.apache.org/docs/apache-airflow-providers-apache-kafka/stable/index.html)
- [NiFi REST API Documentation](https://nifi.apache.org/docs/nifi-docs/rest-api/index.html)
- [Kafka SASL Authentication](https://kafka.apache.org/documentation/#security_sasl)
