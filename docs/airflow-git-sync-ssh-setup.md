# Git-Sync với SSH cho Private GitHub Repo

## 📋 Chuẩn bị

### Bước 1: Tạo Private GitHub Repository

```bash
# Tùy chọn 1: Tạo repo mới trên GitHub Web UI
# - Truy cập: https://github.com/new
# - Repository name: airflow-dags
# - Visibility: Private ✓
# - Click "Create repository"

# Tùy chọn 2: Hoặc sử dụng GitHub CLI
gh repo create airflow-dags --private
```

### Bước 2: Push DAGs lên GitHub

```bash
cd /mnt/d/data-platform/airflow

# Init git (nếu chưa có)
git init
git add dags/
git commit -m "Initial DAGs"

# Add remote và push
git remote add origin git@github.com:thaihung110/airflow-dags.git
git branch -M main
git push -u origin main
```

---

## 🔑 Cấu hình SSH Keys

### Bước 3: Tạo SSH Key pair

```bash
# Tạo SSH key
ssh-keygen -t rsa -b 4096 -C "your_email@example.com" -f ~/.ssh/airflow-git-sync -N ""

# Output:
# - Private key: ~/.ssh/airflow-git-sync
# - Public key: ~/.ssh/airflow-git-sync.pub
```

### Bước 4: Add Public Key vào GitHub

```bash
# Copy public key
cat ~/.ssh/airflow-git-sync.pub

# Thêm vào GitHub:
# 1. Truy cập: https://github.com/thaihung110/airflow-dags/settings/keys
# 2. Click "Add deploy key"
# 3. Title: "Airflow Git-Sync"
# 4. Key: <paste public key>
# 5. ✓ Allow write access (nếu cần)
# 6. Click "Add key"
```

### Bước 5: Convert Private Key sang Base64

```bash
# Convert private key
base64 ~/.ssh/airflow-git-sync -w 0 > /tmp/private-key-base64.txt

# Copy base64 string
cat /tmp/private-key-base64.txt
# Output: LS0tLS1CRUdJTiBPUEVOU1NIIFBSSVZBVEUgS0VZLS0tLS0K...
```

---

## ⚙️ Cấu hình Airflow Helm Chart

### Bước 6: Cập nhật `airflow.yaml`

Mở file `d:\data-platform\infra\k8s\orchestration\config\airflow.yaml` và sửa section `dags`:

```yaml
dags:
  persistence:
    enabled: false # Tắt persistence

  gitSync:
    enabled: true

    # Repository SSH URL
    repo: git@github.com:thaihung110/airflow-dags.git

    branch: main
    rev: HEAD
    depth: 1
    maxFailures: 0

    # Subpath chứa DAGs
    subPath: "dags"

    # SSH Key Secret
    sshKeySecret: airflow-ssh-secret

    # Sync interval
    period: 60s
    wait: 60

    # Resources
    resources:
      limits:
        cpu: 100m
        memory: 128Mi
      requests:
        cpu: 50m
        memory: 64Mi

# Tạo secret chứa SSH private key
extraSecrets:
  airflow-ssh-secret:
    data: |
      gitSshKey: '<paste-base64-private-key-here>'
```

**⚠️ Lưu ý**: Thay `<paste-base64-private-key-here>` bằng base64 string từ Bước 5.

---

## 🚀 Deploy

### Bước 7: Upgrade Airflow

```bash
cd /mnt/d/data-platform

# Upgrade Helm chart
helm upgrade openhouse-airflow apache-airflow/airflow \
  -n default \
  -f infra/k8s/orchestration/config/airflow.yaml \
  --timeout 10m

# Restart pods
kubectl rollout restart deployment/openhouse-airflow-scheduler -n default
kubectl rollout restart deployment/openhouse-airflow-dag-processor -n default
kubectl rollout restart statefulset/openhouse-airflow-worker -n default
```

---

## ✅ Verify

### Bước 8: Kiểm tra Git-Sync

```bash
# 1. Kiểm tra secret
kubectl get secret airflow-ssh-secret -n default

# 2. Xem git-sync logs
SCHEDULER_POD=$(kubectl get pods -n default | grep scheduler | grep Running | awk '{print $1}')
kubectl logs $SCHEDULER_POD -n default -c git-sync --tail=30

# 3. Kiểm tra DAGs
kubectl exec -it $SCHEDULER_POD -n default -c scheduler -- \
  ls -la /opt/airflow/dags/repo/dags/

# 4. Port-forward Airflow UI
kubectl port-forward svc/openhouse-airflow-webserver 8080:8080 -n default
# Truy cập: http://localhost:8080
```

### Logs thành công:

```
INFO: syncing from "git@github.com:thaihung110/airflow-dags.git"
INFO: cloning into "/tmp/git"
INFO: synced 3 files from "origin/main"
```

---

## 🔧 Troubleshooting

### Lỗi: "Permission denied (publickey)"

**Nguyên nhân**: SSH key chưa được add vào GitHub hoặc sai format.

**Fix**:

```bash
# Test SSH connection
ssh -T git@github.com -i ~/.ssh/airflow-git-sync

# Kết quả mong đợi:
# Hi thaihung110! You've successfully authenticated...
```

### Lỗi: "Repository not found"

**Nguyên nhân**: Repository không tồn tại hoặc URL sai.

**Fix**: Kiểm tra repo tồn tại:

```bash
# Clone thử
git clone git@github.com:thaihung110/airflow-dags.git /tmp/test-clone
```

### Lỗi: "Failed to decode secret"

**Nguyên nhân**: Base64 string sai format.

**Fix**:

```bash
# Tạo lại base64 KHÔNG có line breaks
base64 ~/.ssh/airflow-git-sync -w 0 > /tmp/key.txt

# Verify decode
base64 -d /tmp/key.txt | head -5
# Phải hiển thị: -----BEGIN OPENSSH PRIVATE KEY-----
```

---

## 📝 Tóm tắt

**3 bước chính:**

1. ✅ **Tạo SSH keys** và add public key vào GitHub Deploy Keys
2. ✅ **Convert private key** sang base64 và thêm vào `extraSecrets` trong `airflow.yaml`
3. ✅ **Upgrade Helm chart** với cấu hình mới

**Cấu trúc file `airflow.yaml` cần có:**

```yaml
dags:
  gitSync:
    enabled: true
    repo: git@github.com:<username>/<repo>.git
    sshKeySecret: airflow-ssh-secret

extraSecrets:
  airflow-ssh-secret:
    data: |
      gitSshKey: '<base64-private-key>'
```

**Ưu điểm SSH so với HTTPS:**

- ✅ An toàn hơn (không cần lưu password/token)
- ✅ Không bị rate limit từ GitHub
- ✅ Quản lý quyền truy cập tốt hơn với Deploy Keys

---

## 🔄 Alternative: Sử dụng Kubernetes Secret riêng

Thay vì dùng `extraSecrets`, bạn có thể tạo secret riêng:

```bash
# Tạo secret từ file
kubectl create secret generic airflow-ssh-secret \
  --from-file=gitSshKey=$HOME/.ssh/airflow-git-sync \
  -n default

# Hoặc từ base64 string
kubectl create secret generic airflow-ssh-secret \
  --from-literal=gitSshKey="$(base64 -w 0 < ~/.ssh/airflow-git-sync)" \
  -n default
```

Sau đó trong `airflow.yaml` chỉ cần:

```yaml
dags:
  gitSync:
    enabled: true
    repo: git@github.com:thaihung110/airflow-dags.git
    sshKeySecret: airflow-ssh-secret
    # Không cần extraSecrets
```

---

## 📚 Tài liệu tham khảo

- [Airflow Helm Chart - Git-Sync](https://airflow.apache.org/docs/helm-chart/stable/manage-dags-files.html#mounting-dags-from-a-private-github-repo-using-git-sync-sidecar)
- [GitHub Deploy Keys](https://docs.github.com/en/developers/overview/managing-deploy-keys)
