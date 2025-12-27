# ⚠️ Phân tích lỗi: Airflow Spark Job Submission Failed

## 🔴 LỖI HIỆN TẠI

### Triệu chứng:

```
AirflowException: Pod taxi-ingestion-spark-submit-rzl7ndy6 returned a failure.
Status: Failed
Exit Code: 1
Reason: Error
Container: base (kubectl)
```

### Pod Details:

- **Image**: `bitnamilegacy/kubectl:1.33.4-debian-12-r0`
- **Command**: `kubectl apply -f /mnt/manifests/taxi-data-ingestion.yaml`
- **ServiceAccount**: `openhouse-spark-operator-spark`
- **Status**: Terminated with exit code 1

---

## 🔍 NGUYÊN NHÂN GỐC RỄ

### Problem: **RBAC Permission Denied** ❌

#### Test RBAC:

```bash
kubectl auth can-i create sparkapplications \
  --all-namespaces \
  --as=system:serviceaccount:default:openhouse-spark-operator-spark

# Result: no ❌
```

**ServiceAccount `openhouse-spark-operator-spark` KHÔNG có quyền tạo SparkApplication resources!**

### Why This Happens:

1. **Airflow DAG sử dụng KubernetesPodOperator** để submit Spark job
2. **Pod chạy `kubectl apply`** với ServiceAccount `openhouse-spark-operator-spark`
3. **ServiceAccount này không có ClusterRole/Role** để tạo SparkApplication CRD
4. **kubectl apply fails** với permission denied
5. **Pod returns exit code 1** → Airflow task fails

## 🔧 CÁCH FIX CHI TIẾT

### ⚠️ LƯU Ý QUAN TRỌNG

**Có 2 ServiceAccounts cần permissions:**

1. **`openhouse-spark-operator-spark`** - Dùng bởi **KubernetesPodOperator** để submit Spark job (kubectl apply)
2. **`openhouse-airflow-worker`** - Dùng bởi **SparkKubernetesSensor** trong worker pods để monitor Spark job

→ **CẢ HAI đều cần quyền truy cập SparkApplication resources!**

---

### Bước 1: Tạo ClusterRole

ClusterRole định nghĩa permissions cần thiết:

```bash
cd /mnt/d/data-platform/infra/k8s/orchestration

# Create rbac directory
mkdir -p rbac

# Create ClusterRole
cat > rbac/spark-submit-clusterrole.yaml <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spark-submit-role
  labels:
    app: airflow
    component: spark-submit
rules:
  # Permission to manage SparkApplications
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications"]
    verbs: ["create", "get", "list", "watch", "update", "patch", "delete"]

  # Permission to get/list pods (for monitoring Spark driver/executor pods)
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]

  # Permission to get/list services (for Spark UI service)
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list"]

  # Permission to get configmaps (if SparkApplication needs it)
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
EOF
```

---

### Bước 2: Tạo ClusterRoleBinding (CHO CẢ 2 ServiceAccounts)

**QUAN TRỌNG**: Add **CẢ HAI** ServiceAccounts vào subjects list:

```bash
# Create ClusterRoleBinding
cat > rbac/spark-submit-clusterrolebinding.yaml <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spark-submit-binding
  labels:
    app: airflow
    component: spark-submit
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: spark-submit-role
subjects:
  # ServiceAccount for submitting Spark jobs (KubernetesPodOperator)
  - kind: ServiceAccount
    name: openhouse-spark-operator-spark
    namespace: default
  # ServiceAccount for monitoring Spark jobs (SparkKubernetesSensor in worker pods)
  - kind: ServiceAccount
    name: openhouse-airflow-worker
    namespace: default
EOF
```

---

### Bước 3: Apply RBAC Resources

```bash
# Apply ClusterRole
kubectl apply -f rbac/spark-submit-clusterrole.yaml

# Apply ClusterRoleBinding
kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml
```

**Output mong đợi:**

```
clusterrole.rbac.authorization.k8s.io/spark-submit-role created
clusterrolebinding.rbac.authorization.k8s.io/spark-submit-binding created
```

---

### Bước 4: Verify Permissions

**Test cả HAI ServiceAccounts:**

```bash
# Test 1: Permissions cho submit job (openhouse-spark-operator-spark)
kubectl auth can-i create sparkapplications \
  --namespace=default \
  --as=system:serviceaccount:default:openhouse-spark-operator-spark

# Expected: yes ✅

# Test 2: Permissions cho monitor job (openhouse-airflow-worker)
kubectl auth can-i get sparkapplications \
  --namespace=default \
  --as=system:serviceaccount:default:openhouse-airflow-worker

# Expected: yes ✅
```

**View ClusterRoleBinding details:**

```bash
kubectl get clusterrolebinding spark-submit-binding -o yaml
```

Expected output sẽ hiển thị **2 subjects**:

```yaml
subjects:
  - kind: ServiceAccount
    name: openhouse-spark-operator-spark
    namespace: default
  - kind: ServiceAccount
    name: openhouse-airflow-worker
    namespace: default
```

---

### Bước 5: Re-run Airflow DAG

```bash
# Option 1: Trigger from Airflow UI
# 1. Truy cập http://localhost:8080
# 2. Find DAG "taxi-data-ingestion-spark"
# 3. Click "Trigger DAG"
# 4. Monitor tasks:
#    - submit_taxi_ingestion_spark_job (should succeed)
#    - monitor_taxi_ingestion_spark_job (should succeed)

# Option 2: Trigger từ CLI (if airflow CLI available)
airflow dags trigger taxi-data-ingestion-spark
```

---

### Bước 6: Monitor Execution

#### 6.1 Check Submit Task Logs

```bash
# Get Airflow scheduler pod
SCHEDULER_POD=$(kubectl get pods -n default | grep scheduler | awk '{print $1}')

# View logs (or check from Airflow UI)
kubectl logs $SCHEDULER_POD -n default | grep -A 10 "submit_taxi_ingestion_spark_job"
```

**Success logs:**

```
sparkapplication.sparkoperator.k8s.io/taxi-data-ingestion created
```

#### 6.2 Check Monitor Task Logs

From Airflow UI → DAG → Task `monitor_taxi_ingestion_spark_job` → Logs

**Success logs:**

```
INFO - Poking for Spark application taxi-data-ingestion
INFO - Application status: RUNNING
INFO - Application status: COMPLETED
INFO - Success criteria met. Exiting.
```

#### 6.3 Check SparkApplication Status

```bash
# List SparkApplications
kubectl get sparkapplications -n default

# Detailed status
kubectl describe sparkapplication taxi-data-ingestion -n default
```

**Expected statuses:**

- `SUBMITTING` → `RUNNING` → `COMPLETED` (success)
- Or `FAILED` if there's error in Spark job itself

---

## ✅ VERIFY SUCCESS

### Test 1: Check RBAC Applied

```bash
kubectl get clusterrole spark-submit-role
kubectl get clusterrolebinding spark-submit-binding

# Describe to see details
kubectl describe clusterrolebinding spark-submit-binding
```

### Test 2: Manual Test kubectl apply

```bash
# Create a test pod with same ServiceAccount
kubectl run test-spark-submit \
  --image=bitnamilegacy/kubectl:1.33.4-debian-12-r0 \
  --restart=Never \
  --serviceaccount=openhouse-spark-operator-spark \
  -n default \
  --command -- sleep 3600

# Exec into pod
kubectl exec -it test-spark-submit -n default -- bash

# Inside pod, test kubectl
kubectl auth can-i create sparkapplications
# Should return: yes

# Cleanup
exit
kubectl delete pod test-spark-submit -n default
```

### Test 3: Verify SparkApplication Created

```bash
# After running DAG task
kubectl get sparkapplications -n default

# Expected:
# NAME                   STATUS    ATTEMPTS   START                  FINISH   AGE
# taxi-data-ingestion   RUNNING   1          2025-12-26T00:xx:xx            30s
```

### Test 4: Check Airflow Task Logs

From Airflow UI:

1. Go to DAG `taxi-data-ingestion-spark`
2. Click on task `submit_taxi_ingestion_spark_job`
3. View logs

**Success logs should show:**

```
sparkapplication.sparkoperator.k8s.io/taxi-data-ingestion created
```

---

## 📊 TROUBLESHOOTING

### Issue: "still getting permission denied"

**Check**:

```bash
# Verify ClusterRoleBinding
kubectl get clusterrolebinding spark-submit-binding -o yaml

# Ensure subjects.name matches ServiceAccount
# Ensure subjects.namespace is "default"
```

**Fix**:

```bash
# Delete and recreate binding
kubectl delete clusterrolebinding spark-submit-binding
kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml
```

### Issue: "ServiceAccount not found"

**Check**:

```bash
kubectl get serviceaccount openhouse-spark-operator-spark -n default
```

**If not exists**, check Spark Operator installation:

```bash
kubectl get pods -n spark-operator
kubectl get serviceaccount -A | grep spark
```

### Issue: "SparkApplication CRD not registered"

**Check**:

```bash
kubectl get crd | grep sparkapplication
```

**If not exists**, install Spark Operator:

```bash
helm repo add spark-operator https://googlecloudplatform.github.io/spark-on-k8s-operator
helm install spark-operator spark-operator/spark-operator -n spark-operator --create-namespace
```

### Issue: "SparkKubernetesSensor fails with 403 Forbidden"

**Lỗi hiển thị:**

```
ApiException: (403)
Reason: Forbidden
User "system:serviceaccount:default:openhouse-airflow-worker" cannot get resource "sparkapplications"
```

**Nguyên nhân**: ServiceAccount `openhouse-airflow-worker` không được add vào ClusterRoleBinding

**Check**:

```bash
# Verify airflow-worker có permissions chưa
kubectl auth can-i get sparkapplications \
  --as=system:serviceaccount:default:openhouse-airflow-worker

# Nếu trả về "no" → cần add vào binding
```

**Fix**:

```bash
# View current ClusterRoleBinding
kubectl get clusterrolebinding spark-submit-binding -o yaml

# Nếu chỉ thấy 1 subject, cần add thêm airflow-worker:
kubectl edit clusterrolebinding spark-submit-binding

# Thêm vào subjects list:
# subjects:
# - kind: ServiceAccount
#   name: openhouse-spark-operator-spark
#   namespace: default
# - kind: ServiceAccount
#   name: openhouse-airflow-worker    # ← ADD THIS
#   namespace: default

# Hoặc apply lại file YAML đã sửa:
kubectl apply -f rbac/spark-submit-clusterrolebinding.yaml
```

**Verify fix**:

```bash
# Test lại permission
kubectl auth can-i get sparkapplications \
  --as=system:serviceaccount:default:openhouse-airflow-worker
# Should return: yes

# Re-run DAG task monitor_taxi_ingestion_spark_job
# Should succeed now ✅
```

## 📝 TÓM TẮT

**Vấn đề**:

- ❌ ServiceAccount `openhouse-spark-operator-spark` không có quyền **tạo** SparkApplication (submit task fails)
- ❌ ServiceAccount `openhouse-airflow-worker` không có quyền **đọc** SparkApplication (monitor task fails)

**Giải pháp**: Tạo ClusterRole + ClusterRoleBinding cho **CẢ HAI** ServiceAccounts

**3 bước FIX nhanh**:

1. ✅ **Tạo ClusterRole** với permissions cho SparkApplication
2. ✅ **Tạo ClusterRoleBinding** add CẢ 2 ServiceAccounts vào subjects
3. ✅ **Verify cả 2**:

   ```bash
   # Submit permissions
   kubectl auth can-i create sparkapplications \
     --as=system:serviceaccount:default:openhouse-spark-operator-spark

   # Monitor permissions
   kubectl auth can-i get sparkapplications \
     --as=system:serviceaccount:default:openhouse-airflow-worker
   ```

**Kết quả mong đợi**: Cả 2 đều trả về `yes` ✅

**Files đã tạo**:

- `infra/k8s/orchestration/rbac/spark-submit-clusterrole.yaml`
- `infra/k8s/orchestration/rbac/spark-submit-clusterrolebinding.yaml`

Sau khi fix, re-run Airflow DAG sẽ thành công cho cả 2 tasks:

- ✅ `submit_taxi_ingestion_spark_job` - SparkApplication created
- ✅ `monitor_taxi_ingestion_spark_job` - SparkApplication monitored
