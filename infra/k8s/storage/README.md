## Storage

---

Phần storage:

- [minio](#cài-đặt-minio)
- [postgresql](#cài-đặt-postgresql)
- [keycloak](#cài-đặt-keycloak)
- [openfga](#cài-đặt-openfga)
- [lakekeeper](#cài-đặt-lakekeeper)

### Cài đặt Minio

---

Minio nên cài ngoài bare metal thay vì ảo hóa thêm 1 lớp trên k8s.

- [cài minio trên môi trường enterprise](https://docs.min.io/enterprise/aistor-object-store/installation/linux/install/deploy-aistor-on-ubuntu-server/)
- [cài minio trên môi trường community](https://docs.min.io/community/minio-object-store/operations/deployments/baremetal-deploy-minio-on-ubuntu-linux.html)

Ngoài ra còn một số link bên ngoài về [cài đặt minio](https://kifarunix.com/how-to-install-minio-on-ubuntu-24-04-step-by-step/).

Tạm thời sẽ cài đặt trên k8s: [helm chart bitnami minio](https://artifacthub.io/packages/helm/bitnami/minio), helm version: 17.0.22, minio version: 2025.7.23.

docker images:

- docker.io/bitnami/minio:2025.7.23-debian-12-r3
- docker.io/bitnami/minio-client:2025.7.21-debian-12-r2
- docker.io/bitnami/minio-object-browser:2.0.2-debian-12-r3
- docker.io/bitnami/os-shell:12-debian-12-r50

cài đặt

```shell
./scripts/install_minio.sh
```

user: _admin_, password: _admin123_

### Cài đặt Postgresql

---

Postgres nên cài đặt ngoài bare metal thay vì ảo hóa thêm 1 lớp trên k8s. sử dụng document chính thức của nó để cài.

Tạm thời sẽ cài đặt trên k8s: [helm chart bitnami postgresql](https://artifacthub.io/packages/helm/bitnami/postgresql), helm version: 16.7.26, postgresql version: 17.6.0.

docker images:

- docker.io/bitnami/os-shell:12-debian-12-r50
- docker.io/bitnami/postgres-exporter:0.17.1-debian-12-r15
- docker.io/bitnami/postgresql:17.6.0-debian-12-r0

cài đặt

```shell
./scripts/install_postgresql.sh
```

Tạo 1 database primary và 1 database read. User: _postgres_, password: _admin_.

Tạo thêm user, và database cho các thành phần trong hệ thống.

```postgresql
create database keycloak;
create user keycloak;
alter user keycloak with encrypted password 'keycloak';
alter database keycloak owner to keycloak;

create database catalog;
create user catalog;
alter user catalog with encrypted password 'catalog';
alter database catalog owner to catalog;

create database openfga;
create user openfga;
alter user openfga with encrypted password 'openfga';
alter database openfga owner to openfga;
```

### Cài đặt Keycloak

---

[helm chart bitnami keycloak](https://artifacthub.io/packages/helm/bitnami/keycloak), helm version: 25.2.3, keycloak version: 26.3.3

Docker images:

- docker.io/bitnami/keycloak:26.3.3-debian-12-r0
- docker.io/bitnami/keycloak-config-cli:6.4.0-debian-12-r11

Tạo self-cert cho keycloak

```shell
./scripts/create_secret_keycloak_tls.sh
```

Cài đặt

```shell
./scripts/install_keycloak.sh
```

Một số chú ý khi config:

- vì lakekeeper cần chạy trên https, nên keycloak cũng phải chạy trên https.
- bỏ `KC_HOSTNAME` trong helm chart, comment KC_HOSTNAME trong configmap-env-vars.yaml.
- thêm `proxyHeaders: "xforwarded"` trong file config keycloak.yaml.

#### Keycloak Configuration

**1. Create Realm 'iceberg'**

Access Keycloak admin console and create a new realm named `iceberg`:

![Create Realm Iceberg](../../../assets/create-realm-iceberg.png)

**2. Create Client 'lakekeeper'**

Create a public client for Lakekeeper:

- Client ID: `lakekeeper`
- Client authentication: OFF (public client)

![Create Client Lakekeeper - Step 1](../../../assets/create-client-lakekeeper-1.png)

![Create Client Lakekeeper - Step 2](../../../assets/client-lakekeeper-2.png)

**3. Create Client Scope 'lakekeeper'**

Create a client scope with assigned type: **Default**

![Create Client Scope Lakekeeper](../../../assets/client-scope-lakekeeper-1.png)

Configure mapper for the client scope:

- Go to Client Scope `lakekeeper` → Mappers → Add Mapper → By Configuration
- Select: **Audience**
- Mapper Details:
  - Included Client Audience: `lakekeeper`
  - Add to access token: **ON**

![Mapper Client Scope](../../../assets/mapper-client-scope.png)

**4. Assign Client Scope to Client**

Go back to Client `lakekeeper` → Client Scopes → Add client scope:

- Select: `lakekeeper`
- Assigned type: **Default**

**5. Create Client 'spark' for Spark Jobs**

Create a confidential client for Spark:

- Client ID: `spark`
- Client authentication: **ON**

![Create Client Spark](../../../assets/client-spark.png)

After creation, go to Credentials tab to get the **client secret**:

![Client Spark Credentials](../../../assets/client-spark-2.png)

**6. Create Client Scope 'sign' for Spark**

Create a client scope named `sign`:

- Include in token scope: **ON**

![Client Scope Sign](../../../assets/client-scope-sign.png)

Then add this scope to client `spark`:

- Go to Client `spark` → Client Scopes → Add client scope
- Select: `sign`
- Assigned type: **Default**

**7. Create User**

Go to Users → Create new user:

- Username: `admin`
- Set password: `admin`
- Temporary: **OFF**

### Cài đặt Openfga

---

[helm chart official openfga](https://artifacthub.io/packages/helm/openfga/openfga), helm version: 0.2.35, openfga version: v1.8.16

Docker images:

- docker.io/openfga/openfga:v1.8.16

Cài đặt

```shell
./scripts/install_openfga.sh
```

### Cài đặt Lakekeeper

---

[helm chart official lakekeeper](https://artifacthub.io/packages/helm/lakekeeper/lakekeeper), helm version: 0.7.1, lakekeeper version: 0.9.3

Docker images:

- docker.io/lakekeeper/catalog:v0.9.5

Tạo self-cert cho lakekeeper

```shell
./scripts/create_secret_lakekeeper_tls.sh
```

cài đặt

```shell
./scripts/install_lakekeeper.sh
```

Một số chú ý khi config:

- lakekeeper cần chạy trên https

#### Lakekeeper Configuration

**1. Login and Bootstrap**

Access Lakekeeper UI and login with credentials:

- Username: `admin`
- Password: `admin`

After login, perform **bootstrap** operation on the UI.

**2. Create Warehouse**

Go to Warehouses section and create a new warehouse to connect to MinIO bucket:

![Create Warehouse Lakekeeper - Step 1](../../../assets/create-warehouse-lakekeeper.png)

Configure warehouse connection to MinIO:

![Create Warehouse Lakekeeper - Step 2](../../../assets/create-warehouse-lakekeeper-2.png)

### Cấu hình ingress khi chạy trên wsl

---

Tải Ingress-NGINX controller:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.13.0/deploy/static/provider/cloud/deploy.yaml
```

Chạy minikube tunnel ở một terminal khác:

```bash
sudo -E minikube tunnel
```
