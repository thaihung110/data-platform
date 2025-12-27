## Triển khai Kafka, NiFi, Airflow trên K8s (namespace `default`)

Mô tả ngắn gọn cách chuẩn bị chart, cấu hình và script để cài đặt ba thành phần bằng Helm, phù hợp kiến trúc **không ArgoCD** (kubectl/Helm trực tiếp).

### Thư mục sử dụng

- `@helm` → `infra/k8s/orchestration/helm` (lưu chart `.tgz` đã pull)
- `@config` → `infra/k8s/orchestration/config` (lưu bản sao `values.yaml` để chỉnh sửa)
- `@scripts`→ `infra/k8s/orchestration/scripts` (lưu script install/uninstall/template; tham khảo mẫu sẵn có ở `infra/k8s/compute/scripts`)

### Yêu cầu chung

- Có `kubectl`, `helm`, quyền cài chart vào cluster.
- Dùng namespace `default` (không dùng ArgoCD).
- Đảm bảo có `StorageClass` mặc định và đủ tài nguyên cho từng thành phần.

### Quy trình chung cho mỗi thành phần

1. Pull chart về `@helm`  
   `helm pull <repo>/<chart> -d @helm`

2. Lưu cấu hình mẫu để chỉnh sửa vào `@config`  
   `helm show values <repo>/<chart> > @config/<component>-values.yaml`

3. Cài đặt với file cấu hình đã chỉnh  
   `helm install <release> @helm/<chart>-<version>.tgz -f @config/<component>-values.yaml -n default`

4. Xuất template (tùy chọn)  
   `helm template <release> @helm/<chart>-<version>.tgz -f @config/<component>-values.yaml -n default > @scripts/<component>_template.yaml`

5. Gỡ cài đặt khi cần  
   `helm uninstall <release> -n default`

### Kafka

- Repo: `helm repo add bitnami https://charts.bitnami.com/bitnami`
- Pull: `helm pull bitnami/kafka -d @helm`
- Config: `@config/kafka-values.yaml`
- Install: `helm install kafka @helm/kafka-*.tgz -f @config/kafka-values.yaml -n default`
- Uninstall: `helm uninstall kafka -n default`

### NiFi

- Repo: `helm repo add cetic https://cetic.github.io/helm-charts`
- Pull: `helm pull cetic/nifi -d @helm`
- Config: `@config/nifi-values.yaml`
- Install: `helm install nifi @helm/nifi-*.tgz -f @config/nifi-values.yaml -n default`
- Uninstall: `helm uninstall nifi -n default`

### Airflow

- Repo: `helm repo add apache-airflow https://airflow.apache.org`
- Pull: `helm pull apache-airflow/airflow -d @helm`
- Config: `@config/airflow-values.yaml`
- Install: `helm install airflow @helm/airflow-*.tgz -f @config/airflow-values.yaml -n default`
- Uninstall: `helm uninstall airflow -n default`

### Gợi ý script trong `@scripts`

Tạo các script (quyền thực thi) theo mẫu:

- `install_kafka.sh`, `install_nifi.sh`, `install_airflow.sh` → chạy bước pull (nếu cần), rồi `helm install`.
- `uninstall_kafka.sh`, `uninstall_nifi.sh`, `uninstall_airflow.sh` → chạy `helm uninstall`.
- `template_kafka.sh`, `template_nifi.sh`, `template_airflow.sh` → chạy `helm template` để xuất manifest YAML phục vụ review/`kubectl apply`.

Giữ cú pháp tương tự các script mẫu ở `infra/k8s/compute/scripts` (shebang, kiểm tra thư mục, in log ngắn gọn).
