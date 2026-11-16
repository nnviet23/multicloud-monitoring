Used MCP tool: kali-vm/ssh_connections
Analyzed ssh_connections.json:L1
Used MCP tool: kali-vm/ssh_connections
Analyzed REFACTORING_v3.md
Analyzed REFACTORING_CHECKLIST.md:L1-89
Analyzed 03-statefulset-prometheus.yaml:L1-60
Analyzed 03-statefulset-prometheus.yaml:L61-103

Rất tốt! Chúng ta sẽ bắt đầu ngay với **Phương án A (Minimal Refactoring)** để xử lý triệt để các xung đột biến môi trường trong `.env`, xóa bỏ mật khẩu plaintext trong `objstore.yml`, và chuẩn hóa toàn bộ các manifest liên quan nhằm đảm bảo hệ thống vận hành trơn tru mà không làm gián đoạn bất kỳ luồng dữ liệu nào.

Dưới đây là chi tiết từng bước chuẩn hóa và mã nguồn cụ thể cho từng tệp.

---

### Bước 1: Chuẩn hóa tệp `.env` & `.env.example` (Single Source of Truth)

Chúng ta loại bỏ hoàn toàn các biến dư thừa (`admin-user`, `admin-password`, `telegram_bot_token`, `telegram_chat_id`), chỉ giữ lại duy nhất một quy chuẩn đặt tên chuẩn ngành (SCREAMING_SNAKE_CASE).

#### Nội dung tệp `.env`:
```properties
# ==============================================================================
# Multi-Cloud Monitoring Platform - Canonical Active Environment Variables
# ==============================================================================

# --- MinIO Object Storage Credentials ---
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=MultiCloudSecurePassword2026!

# --- AWS SDK Standard S3 Access Keys (Thanos, Loki, Tempo & OTel Exporter) ---
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=MultiCloudSecurePassword2026!

# --- Grafana UI Administration Credentials ---
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=MultiCloudSecurePassword2026!

# --- Smart Alerting: Robusta & AI Engine Telegram Integration ---
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# --- Docker Host Gateway IP (CoreDNS NodeHosts Mapping) ---
DOCKER_HOST_GATEWAY_IP=192.168.65.254
```

#### Nội dung tệp `.env.example`:
```properties
# ==============================================================================
# Multi-Cloud Monitoring Platform - Environment Configuration Template
# ==============================================================================
# Copy this file to .env and replace placeholders with secure values.
# DO NOT commit .env containing production secrets to Git.

# --- MinIO Object Storage Credentials ---
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=MultiCloudSecurePassword2026!

# --- AWS SDK Standard S3 Access Keys (Thanos, Loki, Tempo & OTel Exporter) ---
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=MultiCloudSecurePassword2026!

# --- Grafana UI Administration Credentials ---
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=MultiCloudSecurePassword2026!

# --- Smart Alerting: Robusta & AI Engine Telegram Integration ---
TELEGRAM_BOT_TOKEN=CHANGE_ME_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=CHANGE_ME_TELEGRAM_CHAT_ID

# --- Docker Host Gateway IP (CoreDNS NodeHosts Mapping) ---
DOCKER_HOST_GATEWAY_IP=192.168.65.254
```

---

### Bước 2: Khắc phục tệp `k8s/base/metrics-thanos/objstore.yml` (Xóa bỏ Plaintext)

Thanos sử dụng thư viện Go AWS SDK. Khi không khai báo `access_key` và `secret_key` trong file cấu hình, SDK sẽ tự động nạp từ biến môi trường `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY`.

#### Nội dung mới của [k8s/base/metrics-thanos/objstore.yml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/metrics-thanos/objstore.yml):
```yaml
type: S3
config:
  bucket: "thanos-metrics"
  endpoint: "minio.storage.svc.cluster.local:9000"
  insecure: true
```

---

### Bước 3: Nạp biến môi trường cho Thanos Sidecar trong StatefulSet

Trong tệp [k8s/base/metrics-thanos/03-statefulset-prometheus.yaml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/metrics-thanos/03-statefulset-prometheus.yaml#L62-L80), bổ sung khối `env` cho container `thanos-sidecar` nạp từ secret `loki-s3-creds` (secret này được sinh từ `.env`):

```yaml
        - name: thanos-sidecar
          image: quay.io/thanos/thanos:v0.36.1
          imagePullPolicy: IfNotPresent
          args:
            - sidecar
            - --tsdb.path=/data
            - --prometheus.url=http://127.0.0.1:9090
            - --objstore.config-file=/etc/thanos/objstore.yml
            - --shipper.upload-compacted
            - --http-address=0.0.0.0:10902
            - --grpc-address=0.0.0.0:10901
          env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: loki-s3-creds
                  key: AWS_ACCESS_KEY_ID
            - name: AWS_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: loki-s3-creds
                  key: AWS_SECRET_ACCESS_KEY
```

---

### Bước 4: Đồng bộ Secret Key cho Grafana Deployment

Trong tệp [k8s/base/visualization-grafana/03-deployment.yaml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/visualization-grafana/03-deployment.yaml#L23-L33), đổi key sang chuẩn mới:

```yaml
          env:
            - name: GF_SECURITY_ADMIN_USER
              valueFrom:
                secretKeyRef:
                  name: grafana-admin-creds
                  key: GRAFANA_ADMIN_USER
            - name: GF_SECURITY_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: grafana-admin-creds
                  key: GRAFANA_ADMIN_PASSWORD
            - name: GF_USERS_ALLOW_SIGN_UP
              value: "false"
```

---

### Bước 5: Đồng bộ Secret Key cho Robusta Runner

Trong tệp [k8s/base/smart-alerting-robusta/01-secret.yaml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/smart-alerting-robusta/01-secret.yaml#L7-L9):
```yaml
stringData:
  TELEGRAM_BOT_TOKEN: "0000000000:AAH_DUMMY_TOKEN_REPLACE_ME"
  TELEGRAM_CHAT_ID: "-1001234567890"
```

Và trong [k8s/base/smart-alerting-robusta/03-runner-deployment.yaml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/smart-alerting-robusta/03-runner-deployment.yaml#L38-L47):
```yaml
            - name: TELEGRAM_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: robusta-secrets
                  key: TELEGRAM_BOT_TOKEN
            - name: TELEGRAM_CHAT_ID
              valueFrom:
                secretKeyRef:
                  name: robusta-secrets
                  key: TELEGRAM_CHAT_ID
```

---

### Bước 6: Cập nhật `Makefile` để tự động nạp `.env` vào Ansible

Trong [Makefile](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/Makefile#L51-L57), cập nhật target `infra` để nạp tệp `.env` trước khi thực thi Ansible:

```makefile
.PHONY: infra
infra: pki-generate ## Provision 3 k3d clusters, WAN bridge, CoreDNS & mTLS secrets via Ansible
	@echo "--> Provisioning infrastructure via Ansible master playbook..."
	@set -a; [ -f .env ] && . ./.env; set +a; \
	ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/site.yml
	@echo "Importing container images into freshly provisioned clusters..."
	@$(MAKE) import-images
```

Và cập nhật target `deploy-hub` để luôn đảm bảo đồng bộ `.env` mới nhất vào overlay:
```makefile
.PHONY: deploy-hub
deploy-hub: env-setup ## Deploy complete Hub Observability Stack via Kustomize Overlay
	@echo "--> Deploying Hub Observability Stack on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) apply -k k8s/overlays/local-k3d/hub
```

---

### Nội dung lưu vào tài liệu `docs/refactoring/REFACTORING_v3.md` (Tệp bạn đang mở)

Bạn có thể dán toàn bộ nội dung kế hoạch thực thi này vào tệp [REFACTORING_v3.md](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/docs/refactoring/REFACTORING_v3.md):

```markdown
# KẾ HOẠCH THỰC THI TÁI CẤU TRÚC PHƯƠNG ÁN A
## (Minimal Refactoring & Canonical Environment Standardization)

> **Mục tiêu:** Chuẩn hóa toàn diện hệ thống cấu hình bí mật .env, loại bỏ mật khẩu plaintext trong Thanos objstore.yml, đồng bộ hóa quy ước đặt tên cho Grafana/Robusta/AI Engine, và khắc phục cơ chế truyền biến môi trường trong Makefile & Ansible.

### 1. Danh sách tệp cần cập nhật:
1. `.env`: Chuẩn hóa 5 nhóm biến duy nhất, xóa bỏ các biến thừa.
2. `.env.example`: Đồng bộ với template chuẩn mới.
3. `k8s/base/metrics-thanos/objstore.yml`: Xóa bỏ access_key & secret_key hardcode, chuyển sang dùng AWS Go SDK credential chain.
4. `k8s/base/metrics-thanos/03-statefulset-prometheus.yaml`: Nạp AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY vào container thanos-sidecar.
5. `k8s/base/visualization-grafana/03-deployment.yaml`: Ánh xạ key sang GRAFANA_ADMIN_USER & GRAFANA_ADMIN_PASSWORD.
6. `k8s/base/smart-alerting-robusta/01-secret.yaml` & `03-runner-deployment.yaml`: Ánh xạ key sang TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID.
7. `Makefile`: Nạp tự động .env cho Ansible và tự động đồng bộ sang Kustomize overlay.

### 2. Các bước kiểm chứng sau khi cập nhật:
- Chạy `make validate-kustomize`: Đảm bảo tất cả manifests build thành công 100%.
- Chạy `make validate-dashboards`: Đảm bảo 8 Dashboards Grafana không bị ảnh hưởng.
- Chạy `make deploy-hub`: Nạp lại cấu hình các thành phần quan sát trên hub-k3d.
- Kiểm tra pods: Đảm bảo `prometheus-0`, `thanos-query`, `grafana`, `robusta-runner` đều đạt `1/1` và `2/2 Running`.
- Kiểm tra kết nối S3: Lệnh `mc ls local/thanos-metrics` xác nhận Thanos tiếp tục upload TSDB bình thường.
```

Sau khi bạn đã lưu các tệp trên, hãy cho tôi biết để chúng ta chạy lệnh kiểm tra `make validate-kustomize` và tiến hành các bước kiểm chứng tiếp theo!

---

## PHẦN BỔ SUNG: BÁO CÁO ĐỐI CHIẾU THỰC TẾ & ĐỀ XUẤT CẬP NHẬT KỸ THUẬT (AUDIT ADDENDUM)

*Ngày lập:* 15/11/2026  
*Nội dung:* Kết quả kiểm tra sâu toàn bộ mã nguồn thực tế, đối chiếu 6 tầng kiến trúc, kiểm định tính khả thi của các bước trong Phương án A và bổ sung các phát hiện quan trọng.

### 1. Kết quả đối chiếu các tầng kiến trúc thực tế (Architecture Cross-Verification)
- **Tầng Infrastructure:**
  - `infra/ansible/`: 8 playbooks (`00` đến `06`, `99`, `site.yml`) + `inventory.ini`. Playbook `04_sync_cluster_hosts.yml` dùng `lookup('env', 'DOCKER_HOST_GATEWAY_IP')`.
  - `security/pki/`: Bộ 3 script sinh Root CA, chứng chỉ Hub mTLS 1.3 và Spoke certs hoàn chỉnh.
  - `infra/scripts/`: 3 scripts kéo, nạp và dọn dẹp image container hoạt động tốt.
- **Tầng Kubernetes:**
  - `k8s/base/`: 9 cụm tài nguyên (`storage-minio`, `metrics-thanos`, `logs-loki`, `traces-tempo`, `visualization-grafana`, `slo-pyrra`, `smart-alerting-robusta`, `otel-collector/gateway`, `otel-collector/edge`, và `teastore` với 8 folder con). Đúng theo báo cáo 03.
  - `k8s/overlays/local-k3d/`: Gồm `hub`, `spoke-aws`, `spoke-azure`.
- **Tầng Observability:**
  - MinIO (S3 storage: 4 buckets), Thanos Sidecar & Query, Loki, Tempo, Grafana (8 Dashboards SRE), Pyrra SLO, Robusta Smart Alerting, OTel Hub Gateway & Edge Collectors.
- **Tầng AI Engine:**
  - Hoạt động độc lập tại `ai-engine/` (mô hình GRU + TCN + Isolation Forest, Prometheus exporter :9108, Tempo trace RCA).
- **Tầng Workloads & Experiments:**
  - `tests/locust/`: Sinh tải benchmark.
  - `tests/chaos/`: Tiêm lỗi WAN, JVM agent (`FaultAgent.java`), MySQL lock và test suite.
- **Tầng Docs:**
  - Tài liệu kiến trúc, đặc tả schemas (`docs/schemas/`), tiến độ triển khai và refactoring.

---

### 2. Các phát hiện kỹ thuật mới & Điểm cần hiệu chỉnh so với đề xuất ban đầu:

#### Phát hiện 1 [CRITICAL]: Thanos bắt buộc cờ `aws_sdk_auth: true` trong `objstore.yml`
- **Vấn đề:** Trong Bước 2 ban đầu, `objstore.yml` chỉ xóa bỏ `access_key` và `secret_key`. Tuy nhiên, trong Thanos (sử dụng AWS SDK Go), khi bỏ credentials tĩnh trong file YAML thì **bắt buộc phải khai báo `aws_sdk_auth: true`**. Nếu thiếu cờ này, Thanos sẽ không kích hoạt chuỗi tìm kiếm biến môi trường AWS SDK (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) và sẽ gây lỗi xác thực hoặc cố kết nối Anonymous, dẫn đến `403 AccessDenied`.
- **Hiệu chỉnh chuẩn xác cho `objstore.yml`:**
  ```yaml
  type: S3
  config:
    bucket: "thanos-metrics"
    endpoint: "minio.storage.svc.cluster.local:9000"
    insecure: true
    aws_sdk_auth: true
  ```

#### Phát hiện 2 [ARCHITECTURAL SMELL]: Triệt tiêu ghép nối bí mật (Coupling Smell)
- **Vấn đề:** Trong Bước 3 ban đầu, Thanos Sidecar được đề xuất mount `secretKeyRef` từ `loki-s3-creds`. Đồng thời, OTel Hub Gateway (`k8s/base/otel-collector/gateway/04-deployment.yaml`) cũng đang `envFrom: - secretRef: name: loki-s3-creds`. Điều này vi phạm nghiêm trọng mục SEC-04 trong tài liệu 03 ("Tách Secret riêng cho OTel Hub Gateway, chấm dứt việc mount ké loki-s3-creds") và làm trầm trọng thêm việc phụ thuộc chéo.
- **Hiệu chỉnh đề xuất:**
  - Trong `k8s/overlays/local-k3d/hub/kustomization.yaml`: bổ sung sinh 2 Secret độc lập từ `.env`:
    - `thanos-s3-creds` cho `metrics-thanos`
    - `otel-s3-creds` cho `otel-collector-hub`
  - Manifest `03-statefulset-prometheus.yaml` nạp từ `thanos-s3-creds`.
  - Manifest `k8s/base/otel-collector/gateway/04-deployment.yaml` nạp từ `otel-s3-creds`.
  - Giúp từng thành phần hoàn toàn độc lập theo đúng nguyên tắc Single Responsibility Principle (SRP).

#### Phát hiện 3 [K8S SECURITY RESTRICTION]: Giới hạn của Kustomize đối với tệp ngoài thư mục
- **Vấn đề:** Mục SEC-05 trong tài liệu 03 đề xuất xóa bỏ tệp bản sao `k8s/overlays/local-k3d/hub/.env` và trỏ trực tiếp về `../../../../.env`. Qua kiểm nghiệm thực tế bằng lệnh `kubectl kustomize`, thao tác này **bị chặn đứng bởi cơ chế bảo mật của kubectl/kustomize**:
  `security error: accumulation err: file is not in or below 'k8s/overlays/local-k3d/hub'` (LoadRestrictionsRootOnly).
- **Giải pháp tối ưu:** 
  - Giữ cơ chế sync tệp `.env` vào `k8s/overlays/local-k3d/hub/.env` thông qua Makefile `env-setup`.
  - Ràng buộc target `deploy-hub: env-setup` và `deploy: env-setup deploy-hub deploy-spokes` trong `Makefile`. Nhờ đó, bất cứ khi nào chạy deploy, `.env` ở root sẽ được tự động đồng bộ ngay lập tức vào overlay, loại bỏ 100% rủi ro trôi lệch cấu hình (Config Drift) mà không vi phạm cơ chế bảo mật của Kustomize.

#### Phát hiện 4 [MAKEFILE BEST PRACTICE]: Tự động xuất biến môi trường toàn cục
- **Vấn đề:** Đề xuất ban đầu dùng cú pháp shell `@set -a; [ -f .env ] && . ./.env; set +a;` chỉ áp dụng cục bộ trong target `infra`.
- **Giải pháp tối ưu:** Thêm khối nạp toàn cục ở đầu `Makefile`:
  ```makefile
  ifneq (,$(wildcard ./.env))
    include .env
    export
  endif
  ```
  Nhờ đó, TẤT CẢ các target trong Makefile (`infra`, `test`, `verify`, các script con) đều tự động nhận đầy đủ các biến từ `.env` mà không cần chèn lệnh shell thủ công.

#### Phát hiện 5 [CHỈNH LÝ CHÚ THÍCH BIẾN .env]: Làm rõ đối tượng sử dụng
- Trong `.env`, nhóm biến S3:
  - `MINIO_ROOT_USER` & `MINIO_ROOT_PASSWORD`: Được dùng bởi MinIO (gốc), Loki (`${MINIO_ROOT_USER}`), và Tempo (`${MINIO_ROOT_USER}`).
  - `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY`: Được dùng trực tiếp bởi Thanos Sidecar và OTel Hub Collector (`awss3` exporter).
  - Cần ghi chú rõ điều này trong `.env` và `.env.example` để người vận hành không bị nhầm lẫn.

---

### 3. Tóm tắt Kế hoạch Triển khai Hoàn chỉnh (Action Plan v4.1)

| Bước | Thành phần | Tệp tác động | Hành động chi tiết |
|:---:|---|---|---|
| **1** | Root Environment | `.env` & `.env.example` | Giữ 5 nhóm biến chuẩn: `MINIO_ROOT_*`, `AWS_*`, `GRAFANA_ADMIN_*`, `TELEGRAM_*`, `DOCKER_HOST_GATEWAY_IP`. Xóa biến thừa chữ thường và kebab-case. Làm rõ chú thích. |
| **2** | Makefile | `Makefile` | Thêm `include .env` & `export` toàn cục; gắn `env-setup` làm dependency của `deploy-hub` và `deploy`. |
| **3** | Thanos S3 Storage | `k8s/base/metrics-thanos/objstore.yml` | Bỏ access_key/secret_key plaintext; thêm `aws_sdk_auth: true`. |
| **4** | Thanos StatefulSet | `k8s/base/metrics-thanos/03-statefulset-prometheus.yaml` | Nạp `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` từ `thanos-s3-creds`. |
| **5** | OTel Hub Gateway | `k8s/base/otel-collector/gateway/04-deployment.yaml` | Đổi `envFrom` từ `loki-s3-creds` sang `otel-s3-creds` (giải quyết triệt để SEC-04). |
| **6** | Hub Overlay | `k8s/overlays/local-k3d/hub/kustomization.yaml` | Bổ sung sinh 2 secret riêng biệt `thanos-s3-creds` và `otel-s3-creds` từ `.env`. |
| **7** | Grafana Deployment | `k8s/base/visualization-grafana/03-deployment.yaml` | Đổi secret key sang `GRAFANA_ADMIN_USER` và `GRAFANA_ADMIN_PASSWORD`. |
| **8** | Robusta Runner | `k8s/base/smart-alerting-robusta/01-secret.yaml` & `03-runner-deployment.yaml` | Đổi secret key sang `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID`. |
| **9** | Kiểm định | Toàn hệ thống | Chạy `make validate-kustomize`, `make validate-dashboards`, `kubectl kustomize`. |
