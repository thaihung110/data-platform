# Đề Xuất Điều Chỉnh Folder Structure

## Phân Tích Hiện Trạng

### Cấu trúc hiện tại (`infra/k8s/`):

```
infra/k8s/
├── compute/          # Compute resources (ArgoCD, Spark Operator)
│   ├── applications/     # SparkApplication manifests
│   ├── config/            # Config files
│   ├── debug/             # Debug manifests
│   ├── helm/              # Helm charts (argo-cd, spark-operator)
│   ├── scripts/           # Installation scripts
│   └── test_template/     # Template files
└── storage/          # Storage services (MinIO, PostgreSQL, Keycloak, etc.)
    ├── config/
    ├── debug/
    ├── helm/
    ├── scripts/
    ├── test_template/
    └── tls/
```

### Yêu cầu từ Design Doc:

- Tổ chức SparkApplication theo **bronze/silver/gold layers**
- Dynamic jobs được push bởi Airflow vào `jobs/` subfolder
- ArgoCD Application manifests riêng biệt
- Chuẩn bị cho Airflow integration

---

## Đề Xuất Cấu Trúc Mới

### 0. Tại sao đặt `orchestration/` cùng level với `compute/` và `storage/`?

**Phân loại theo chức năng (Functional Classification):**

| Folder               | Chức năng                         | Components                              | Lý do                                                |
| -------------------- | --------------------------------- | --------------------------------------- | ---------------------------------------------------- |
| **`compute/`**       | Quản lý và chạy compute workloads | ArgoCD, Spark Operator                  | Quản lý việc thực thi jobs, không phải orchestration |
| **`storage/`**       | Lưu trữ dữ liệu và metadata       | MinIO, PostgreSQL, Keycloak, Lakekeeper | Persistent storage và metadata services              |
| **`orchestration/`** | Điều phối workflows và data flows | Airflow, NiFi, Kafka                    | Orchestrate toàn bộ data pipeline                    |

**Ưu điểm:**

- ✅ **Phân loại rõ ràng**: Mỗi folder đại diện cho một lớp chức năng riêng biệt
- ✅ **Dễ mở rộng**: Có thể thêm NiFi, Kafka vào `orchestration/` sau
- ✅ **Logical separation**: Airflow không phải compute resource, nó là orchestration layer
- ✅ **Consistent pattern**: Tất cả đều có `helm/`, `config/`, `scripts/` structure
- ✅ **Scalable**: Dễ thêm các orchestration tools khác (Prefect, Dagster, etc.)

**So sánh với đặt trong `compute/orchestration/`:**

- ❌ Airflow không phải compute resource
- ❌ Làm `compute/` folder quá lớn và phức tạp
- ❌ Khó phân biệt giữa "compute management" (ArgoCD) và "orchestration" (Airflow)

---

### 1. Cấu trúc tổng thể (3-layer architecture: compute/storage/orchestration)

```
infra/k8s/
├── compute/
│   ├── applications/              # ← ĐIỀU CHỈNH: Tổ chức theo layers
│   │   ├── README.md
│   │   │
│   │   ├── bronze-layer/          # ← MỚI: Bronze layer jobs
│   │   │   ├── template.yaml      # Template cho Airflow generate
│   │   │   ├── values.yaml        # Default values
│   │   │   ├── kustomization.yaml # Kustomize config (nếu dùng)
│   │   │   └── jobs/              # ← Dynamic jobs từ Airflow
│   │   │       ├── .gitkeep       # Giữ folder trong Git
│   │   │       └── README.md       # Hướng dẫn
│   │   │
│   │   ├── silver-layer/          # ← MỚI: Silver layer jobs
│   │   │   ├── template.yaml
│   │   │   ├── values.yaml
│   │   │   ├── kustomization.yaml
│   │   │   └── jobs/
│   │   │
│   │   ├── gold-layer/            # ← MỚI: Gold layer jobs
│   │   │   ├── template.yaml
│   │   │   ├── values.yaml
│   │   │   ├── kustomization.yaml
│   │   │   └── jobs/
│   │   │
│   │   └── legacy/                 # ← MỚI: Giữ các jobs cũ (như taxi-data-ingestion.yaml)
│   │       └── taxi-data-ingestion.yaml
│   │
│   ├── argocd/                    # ← MỚI: ArgoCD Application configs
│   │   ├── applications/          # ArgoCD Application manifests
│   │   │   ├── spark-jobs-bronze.yaml
│   │   │   ├── spark-jobs-silver.yaml
│   │   │   ├── spark-jobs-gold.yaml
│   │   │   └── README.md
│   │   │
│   │   ├── projects/              # ArgoCD Projects (nếu cần)
│   │   │   └── data-platform-project.yaml
│   │   │
│   │   └── config/                # ArgoCD ConfigMaps, RBAC
│   │       ├── argocd-cm.yaml
│   │       └── argocd-rbac.yaml
│   │
│   ├── config/                    # Giữ nguyên
│   │   ├── argo.yaml
│   │   └── spark.yaml
│   │
│   ├── debug/                     # Giữ nguyên
│   │   └── spark_controller.yaml
│   │
│   ├── helm/                      # Giữ nguyên
│   │   ├── argo-cd/
│   │   └── spark-operator/
│   │
│   ├── scripts/                    # Giữ nguyên
│   │   ├── install_argocd.sh
│   │   ├── install_spark_operators.sh
│   │   └── ...
│   │
│   └── test_template/             # Giữ nguyên
│       ├── argocd_template.yaml
│       └── spark_operator_template.yaml
│
├── storage/                       # Giữ nguyên cấu trúc hiện tại
│   ├── config/
│   ├── debug/
│   ├── helm/
│   ├── scripts/
│   ├── test_template/
│   └── tls/
│
└── orchestration/                  # ← MỚI: Orchestration layer (cùng structure với compute/storage)
    ├── config/                     # Config files (giống compute/config, storage/config)
    │   ├── airflow.yaml
    │   ├── nifi.yaml
    │   └── kafka.yaml
    │
    ├── debug/                      # Debug manifests (giống compute/debug, storage/debug)
    │   ├── event_airflow.yaml
    │   ├── event_nifi.yaml
    │   └── event_kafka.yaml
    │
    ├── helm/                       # Helm charts (giống compute/helm, storage/helm)
    │   ├── airflow/
    │   ├── nifi/
    │   └── kafka/
    │
    ├── scripts/                    # Installation scripts (giống compute/scripts, storage/scripts)
    │   ├── install_airflow.sh
    │   ├── install_nifi.sh
    │   ├── install_kafka.sh
    │   ├── template_airflow.sh
    │   ├── template_nifi.sh
    │   ├── template_kafka.sh
    │   ├── uninstall_airflow.sh
    │   ├── uninstall_nifi.sh
    │   └── uninstall_kafka.sh
    │
    └── test_template/              # Template files (giống compute/test_template, storage/test_template)
        ├── airflow_template.yaml
        ├── nifi_template.yaml
        └── kafka_template.yaml
```

### 2. Cấu trúc cho Orchestration (tuân theo pattern compute/storage)

```
infra/k8s/
└── orchestration/                  # ← MỚI: Orchestration layer (cùng level với compute/storage)
    ├── config/                     # Config files (giống compute/config, storage/config)
    │   ├── airflow.yaml
    │   ├── nifi.yaml
    │   └── kafka.yaml
    │
    ├── debug/                      # Debug manifests (giống compute/debug, storage/debug)
    │   ├── event_airflow.yaml
    │   └── event_kafka.yaml
    │
    ├── helm/                       # Helm charts (giống compute/helm, storage/helm)
    │   ├── airflow/
    │   ├── nifi/
    │   └── kafka/
    │
    ├── scripts/                    # Installation scripts (giống compute/scripts, storage/scripts)
    │   ├── install_airflow.sh
    │   ├── install_nifi.sh
    │   ├── install_kafka.sh
    │   ├── template_airflow.sh
    │   ├── template_nifi.sh
    │   ├── template_kafka.sh
    │   ├── uninstall_airflow.sh
    │   ├── uninstall_nifi.sh
    │   └── uninstall_kafka.sh
    │
    └── test_template/              # Template files (giống compute/test_template, storage/test_template)
        ├── airflow_template.yaml
        ├── nifi_template.yaml
        └── kafka_template.yaml
```

### 3. Cấu trúc cho Kubernetes resources (nếu cần tách riêng)

```
infra/k8s/
└── shared/                        # ← MỚI: Resources dùng chung
    ├── namespaces/
    │   ├── data-platform.yaml
    │   ├── argocd.yaml
    │   └── airflow.yaml
    │
    ├── secrets/                   # ← Lưu ý: Chỉ templates, không commit secrets thật
    │   ├── minio-credentials-template.yaml
    │   ├── github-token-template.yaml
    │   └── keycloak-credentials-template.yaml
    │
    ├── rbac/
    │   ├── spark-serviceaccount.yaml
    │   └── airflow-rbac.yaml
    │
    └── configmaps/
        ├── spark-config.yaml
        └── external-services.yaml
```

---

## Chi Tiết Điều Chỉnh

### A. Tổ chức lại `compute/applications/`

#### Trước:

```
compute/applications/
└── taxi-data-ingestion.yaml
```

#### Sau:

```
compute/applications/
├── bronze-layer/
│   ├── template.yaml          # Template cho Airflow
│   ├── values.yaml            # Default values
│   ├── kustomization.yaml     # Optional: Kustomize
│   └── jobs/                  # Dynamic jobs từ Airflow
│       └── .gitkeep
│
├── silver-layer/
│   ├── template.yaml
│   ├── values.yaml
│   └── jobs/
│
├── gold-layer/
│   ├── template.yaml
│   ├── values.yaml
│   └── jobs/
│
└── legacy/                    # Di chuyển jobs cũ vào đây
    └── taxi-data-ingestion.yaml
```

### B. Tạo folder `compute/argocd/`

```
compute/argocd/
├── applications/
│   ├── spark-jobs-bronze.yaml      # ArgoCD Application cho bronze layer
│   ├── spark-jobs-silver.yaml      # ArgoCD Application cho silver layer
│   ├── spark-jobs-gold.yaml       # ArgoCD Application cho gold layer
│   └── README.md
│
├── projects/
│   └── data-platform-project.yaml  # ArgoCD Project (nếu cần)
│
└── config/
    ├── argocd-cm.yaml              # ArgoCD ConfigMap
    └── argocd-rbac.yaml            # RBAC policies
```

### C. Template structure cho mỗi layer

#### `bronze-layer/template.yaml`:

```yaml
# Template cho Airflow generate SparkApplication manifests
# Variables: {{ job_id }}, {{ input_path }}, {{ output_path }}, {{ catalog_uri }}

apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: bronze-layer-{{ job_id }}
  namespace: data-platform
  labels:
    app: data-lakehouse
    layer: bronze
    job-id: "{{ job_id }}"
spec:
  # ... spark application spec
```

#### `bronze-layer/values.yaml`:

```yaml
# Default values cho bronze layer
sparkVersion: "3.5.0"
driver:
  cores: 1
  memory: "2g"
executor:
  cores: 2
  instances: 3
  memory: "4g"
warehouse: "bronze"
```

---

## Migration Plan

### Bước 1: Tạo cấu trúc mới

```bash
# Tạo bronze/silver/gold layer folders
mkdir -p infra/k8s/compute/applications/{bronze-layer,silver-layer,gold-layer,legacy}/{jobs}

# Tạo ArgoCD folder
mkdir -p infra/k8s/compute/argocd/{applications,projects,config}

# Tạo orchestration folder (tuân theo pattern compute/storage)
mkdir -p infra/k8s/orchestration/{config,debug,helm/{airflow,nifi,kafka},scripts,test_template}
```

### Bước 2: Di chuyển files hiện tại

```bash
# Di chuyển taxi-data-ingestion.yaml vào legacy
mv infra/k8s/compute/applications/taxi-data-ingestion.yaml \
   infra/k8s/compute/applications/legacy/
```

### Bước 3: Tạo templates

- Tạo `bronze-layer/template.yaml` từ `taxi-data-ingestion.yaml`
- Tạo `silver-layer/template.yaml` và `gold-layer/template.yaml` tương tự
- Tạo `values.yaml` cho mỗi layer

### Bước 4: Tạo ArgoCD Applications

- Tạo `argocd/applications/spark-jobs-bronze.yaml`
- Tạo `argocd/applications/spark-jobs-silver.yaml`
- Tạo `argocd/applications/spark-jobs-gold.yaml`

### Bước 5: Update scripts

- Update `scripts/install_argocd.sh` để apply ArgoCD Applications
- Tạo script mới `scripts/apply_argocd_apps.sh`

---

## Lợi Ích

### 1. **Tổ chức rõ ràng theo layers**

- Dễ quản lý jobs theo bronze/silver/gold
- Tách biệt templates và dynamic jobs

### 2. **GitOps ready**

- ArgoCD Applications riêng biệt cho từng layer
- Dễ dàng sync và rollback

### 3. **Airflow integration**

- Template structure sẵn sàng cho Airflow generate
- `jobs/` folder cho dynamic jobs từ Airflow

### 4. **Backward compatible**

- Giữ `legacy/` folder cho jobs cũ
- Không break existing workflows

### 5. **Consistent với pattern hiện tại**

- Giữ nguyên `compute/` và `storage/` separation
- Thêm `orchestration/` cùng level - phân loại rõ ràng theo chức năng
- Giữ nguyên `helm/`, `scripts/`, `config/` structure trong mỗi folder

### 6. **Phân loại logic theo chức năng**

- **Compute**: ArgoCD, Spark Operator - quản lý và chạy compute workloads
- **Storage**: MinIO, PostgreSQL, Keycloak - lưu trữ dữ liệu và metadata
- **Orchestration**: Airflow, NiFi, Kafka - điều phối workflows và data flows

---

## Next Steps

1. ✅ Review và approve proposal này
2. ⏳ Tạo cấu trúc folders mới
3. ⏳ Di chuyển files hiện tại
4. ⏳ Tạo templates cho bronze/silver/gold
5. ⏳ Tạo ArgoCD Application manifests
6. ⏳ Update documentation
7. ⏳ Test với ArgoCD sync

---

## Notes

- **Secrets**: Không commit secrets thật vào Git, chỉ templates
- **Jobs folder**: Airflow sẽ push dynamic jobs vào `jobs/` subfolder trong `compute/applications/{layer}/jobs/`
- **Kustomize**: Optional, có thể dùng nếu cần advanced manifest management
- **Legacy folder**: Tạm thời giữ jobs cũ, migrate dần dần
- **Orchestration folder**: Đặt cùng level với `compute/` và `storage/` để phân loại rõ ràng theo chức năng
- **Consistent structure**: `orchestration/` tuân theo cùng pattern với `compute/` và `storage/` (config, helm, scripts, debug, test_template)
- **Airflow DAGs**: Thường đặt trong repo riêng hoặc mount từ ConfigMap, không nên đặt trực tiếp trong infra repo

---

## Phân Tích: NiFi và Kafka Nên Để Ở Đâu?

### Apache NiFi

**Vị trí đề xuất: `orchestration/`**

**Lý do:**

- ✅ **Data Flow Orchestration**: NiFi quản lý data flows, không phải compute workload
- ✅ **Workflow Management**: Tương tự Airflow, điều phối data ingestion và transformation flows
- ✅ **Pipeline Orchestration**: Là một phần của orchestration layer trong kiến trúc
- ✅ **Consistent với design doc**: Design doc đặt NiFi trong "ORCHESTRATION LAYER"

**Chức năng trong design doc:**

- Consume raw data từ sources
- Validate và transform data
- Upload to MinIO raw bucket
- Trigger downstream processes

**Kết luận**: Đặt trong `orchestration/` là hợp lý nhất.

---

### Apache Kafka

**Vị trí đề xuất: `orchestration/`**

**Lý do:**

- ✅ **Event Streaming/Message Bus**: Kafka là event bus cho toàn bộ system, không phải storage hay compute
- ✅ **Orchestration Component**: Kết nối các components (Datasource API → Airflow → NiFi)
- ✅ **Workflow Trigger**: Kafka events trigger Airflow DAGs, là một phần của orchestration flow
- ✅ **Consistent với design doc**: Design doc đặt Kafka trong "DATA INGESTION LAYER" nhưng nó phục vụ orchestration

**Chức năng trong design doc:**

- Publish file metadata từ Datasource API
- Airflow listener consume từ Kafka để trigger DAGs
- Event bus cho toàn bộ data pipeline

**Lưu ý:**

- Kafka có thể được coi là "infrastructure" riêng, nhưng trong context này nó phục vụ orchestration
- Nếu scale lớn, có thể tách thành `infrastructure/kafka/` riêng, nhưng hiện tại đặt trong `orchestration/` là đủ

**Kết luận**: Đặt trong `orchestration/` là hợp lý, nhưng có thể tách riêng nếu cần scale lớn.

---

### So Sánh

| Component   | Vị trí           | Lý do                                      |
| ----------- | ---------------- | ------------------------------------------ |
| **Airflow** | `orchestration/` | Workflow orchestration, trigger jobs       |
| **NiFi**    | `orchestration/` | Data flow orchestration, ingestion flows   |
| **Kafka**   | `orchestration/` | Event bus, trigger orchestration workflows |

**Alternative (nếu scale lớn):**

- Tách Kafka thành `infrastructure/kafka/` nếu cần quản lý riêng như infrastructure component
- Nhưng với quy mô hiện tại, đặt trong `orchestration/` là đủ và hợp lý

---

## Phân Tích: NiFi và Kafka Nên Để Ở Đâu?

### Apache NiFi

**Vị trí đề xuất: `orchestration/`**

**Lý do:**

- ✅ **Data Flow Orchestration**: NiFi quản lý data flows, không phải compute workload
- ✅ **Workflow Management**: Tương tự Airflow, điều phối data ingestion và transformation flows
- ✅ **Pipeline Orchestration**: Là một phần của orchestration layer trong kiến trúc
- ✅ **Consistent với design doc**: Design doc đặt NiFi trong "ORCHESTRATION LAYER"

**Chức năng trong design doc:**

- Consume raw data từ sources
- Validate và transform data
- Upload to MinIO raw bucket
- Trigger downstream processes

**Kết luận**: Đặt trong `orchestration/` là hợp lý nhất.

---

### Apache Kafka

**Vị trí đề xuất: `orchestration/`**

**Lý do:**

- ✅ **Event Streaming/Message Bus**: Kafka là event bus cho toàn bộ system, không phải storage hay compute
- ✅ **Orchestration Component**: Kết nối các components (Datasource API → Airflow → NiFi)
- ✅ **Workflow Trigger**: Kafka events trigger Airflow DAGs, là một phần của orchestration flow
- ✅ **Consistent với design doc**: Design doc đặt Kafka trong "DATA INGESTION LAYER" nhưng nó phục vụ orchestration

**Chức năng trong design doc:**

- Publish file metadata từ Datasource API
- Airflow listener consume từ Kafka để trigger DAGs
- Event bus cho toàn bộ data pipeline

**Lưu ý:**

- Kafka có thể được coi là "infrastructure" riêng, nhưng trong context này nó phục vụ orchestration
- Nếu scale lớn, có thể tách thành `infrastructure/kafka/` riêng, nhưng hiện tại đặt trong `orchestration/` là đủ

**Kết luận**: Đặt trong `orchestration/` là hợp lý, nhưng có thể tách riêng nếu cần scale lớn.

---

### So Sánh

| Component   | Vị trí           | Lý do                                      |
| ----------- | ---------------- | ------------------------------------------ |
| **Airflow** | `orchestration/` | Workflow orchestration, trigger jobs       |
| **NiFi**    | `orchestration/` | Data flow orchestration, ingestion flows   |
| **Kafka**   | `orchestration/` | Event bus, trigger orchestration workflows |

**Alternative (nếu scale lớn):**

- Tách Kafka thành `infrastructure/kafka/` nếu cần quản lý riêng như infrastructure component
- Nhưng với quy mô hiện tại, đặt trong `orchestration/` là đủ và hợp lý
