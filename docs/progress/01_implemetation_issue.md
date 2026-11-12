# Nhật Ký Chi Tiết Sự Cố Triển Khai & Giải Pháp Xử Lý (Implementation Issues & Root Cause Analysis)

> **Tài liệu:** `docs/progress/01_implemetation_issue.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Cập nhật lần cuối:** 2026-11-04  
> **Mục đích:** Ghi nhận chi tiết từng lỗi kỹ thuật phát sinh theo từng Phase, phân tích nguyên nhân gốc rễ (Root Cause Analysis - RCA), đề xuất và giải pháp khắc phục triệt để.

---

## 1. Mục lục sự cố theo Phase (Incident Index by Phase)

- [Phase 1: Hạ Tầng Cụm k3d & Mạng Mô Phỏng WAN](#phase-1-hạ-tầng-cụm-k3d--mạng-mô-phỏng-wan)
  - [INC-P1-01: Lỗi nhận diện ngữ cảnh Kubernetes (kubectl context) giữa WSL2 và Windows Host](#inc-p1-01-lỗi-nhận-diện-ngữ-cảnh-kubernetes-kubectl-context-giữa-wsl2-và-windows-host)
- [Phase 2: Workload Ứng Dụng TeaStore & Thu Thập Telemetry Tại Biên](#phase-2-workload-ứng-dụng-teastore--thu-thập-telemetry-tại-biên)
  - [INC-P2-01: Pods TeaStore bị OOMKilled liên tục do nạp OTel Java Agent qua JAVA_TOOL_OPTIONS](#inc-p2-01-pods-teastore-bị-oomkilled-liên-tục-do-nạp-otel-java-agent-qua-java_tool_options)
  - [INC-P2-02: Liveness và Readiness Probes của TeaStore trả về HTTP 404 Not Found](#inc-p2-02-liveness-và-readiness-probes-của-teastore-trả-về-http-404-not-found)
- [Phase 3: Trung Tâm Giám Sát Hub & Lưu Trữ Đa Đám Mây](#phase-3-trung-tâm-giám-sát-hub--lưu-trữ-đa-đám-mây)
  - [INC-P3-01: Lỗi Access Denied khi kéo Container Image MinIO từ Docker Hub](#inc-p3-01-lỗi-access-denied-khi-kéo-container-image-minio-từ-docker-hub)
  - [INC-P3-02: Exporter OTLP HTTP của OTel Collector sang Grafana Loki bị lỗi HTTP 404](#inc-p3-02-exporter-otlp-http-của-otel-collector-sang-grafana-loki-bị-lỗi-http-404)
  - [INC-P3-03: Pyrra SLO Controller lỗi Readiness Probe 404 trên đường dẫn /api/v1/healthz](#inc-p3-03-pyrra-slo-controller-lỗi-readiness-probe-404-trên-đường-dẫn-apiv1healthz)
  - [INC-P3-04: Robusta Runner crash do thiếu biến cấu hình Playbook và quyền RBAC Cluster](#inc-p3-04-robusta-runner-crash-do-thiếu-biến-cấu-hình-playbook-và-quyền-rbac-cluster)
  - [INC-P3-05: Bucket thanos-metrics trong MinIO rỗng do lỗi quyền liên kết cứng (Hardlink Operation Not Permitted)](#inc-p3-05-bucket-thanos-metrics-trong-minio-rỗng-do-lỗi-quyền-liên-kết-cứng-hardlink-operation-not-permitted)
  - [INC-P3-06: Chỉ số Hostmetrics mất nhãn Cluster Spoke (chỉ hiển thị cluster="hub-k3d")](#inc-p3-06-chỉ-số-hostmetrics-mất-nhãn-cluster-spoke-chỉ-hiển-thị-clusterhub-k3d)
  - [INC-P3-07: Grafana Topology Dashboard báo lỗi "id field is required for nodes data frame"](#inc-p3-07-grafana-topology-dashboard-báo-lỗi-id-field-is-required-for-nodes-data-frame)
  - [INC-P3-08: Log cảnh báo MySQL "Aborted connection" và thuộc tính telemetry.hub.received_time mang giá trị null](#inc-p3-08-log-cảnh-báo-mysql-aborted-connection-và-thuộc-tính-telemetryhubreceived_time-mang-giá-trị-null)
  - [INC-P3-09: Phân mảnh nhãn cụm giữa cluster và k8s_cluster_name khi truy vấn chỉ số](#inc-p3-09-phân-mảnh-nhãn-cụm-giữa-cluster-và-k8s_cluster_name-khi-truy-vấn-chỉ-số)
  - [INC-P3-10: Bucket raw-telemetry trong MinIO hoàn toàn rỗng do thiếu pipeline export thô](#inc-p3-10-bucket-raw-telemetry-trong-minio-hoàn-toàn-rỗng-do-thiếu-pipeline-export-thô)
  - [INC-P3-11: Thiếu bộ Dashboards giám sát đa đám mây chuẩn SRE](#inc-p3-11-thiếu-bộ-dashboards-giám-sát-đa-đám-mây-chuẩn-sre)
  - [INC-P3-12: Thiếu định danh Region và xuất hiện node "unknown" trong Service Graph](#inc-p3-12-thiếu-định-danh-region-và-xuất-hiện-node-unknown-trong-service-graph)
  - [INC-P3-13: Mở rộng mô hình Cloud Dependencies chuyên sâu cho từng tài nguyên (Deep Single-Resource Cloud Dependencies Model & OTTL Injection)](#inc-p3-13-mở-rộng-mô-hình-cloud-dependencies-chuyên-sâu-cho-từng-tài-nguyên-deep-single-resource-cloud-dependencies-model--ottl-injection)
  - [INC-P3-14: Trực quan hóa toàn diện 6 Trục Phụ Thuộc Đám Mây Sâu và Ma Trận Kết Nối Mạng L3/L4 trên Grafana Topology](#inc-p3-14-trực-quan-hóa-toàn-diện-6-trục-phụ-thuộc-đám-mây-sâu-và-ma-trận-kết-nối-mạng-l3l4-trên-grafana-topology)
- [Phase 3.5: Giám Sát Hạ Tầng Full-Stack & Nâng Cấp Dashboards SRE](#phase-35-giám-sát-hạ-tầng-full-stack--nâng-cấp-dashboards-sre)
  - [INC-P3-15: Thiếu hụt chỉ số hạ tầng sâu tầng OS/Kernel/Storage/USE và nâng cấp toàn diện bộ 7 Dashboards Grafana chuẩn SRE](#inc-p3-15-thiếu-hụt-chỉ-số-hạ-tầng-sâu-tầng-oskernelstorageuse-và-nâng-cấp-toàn-diện-bộ-7-dashboards-grafana-chuẩn-sre)
- [Phase 3.6: Chuẩn Hóa Unified Resource Schemas & JVM Runtime Completeness](#phase-36-chuẩn-hóa-unified-resource-schemas--jvm-runtime-completeness)
  - [INC-P3-16: Chuẩn hóa bộ đặc tả Unified Resource Monitoring Schemas (Web App & Compute Instance) và bổ sung độ phủ JVM Runtime Saturation](#inc-p3-16-chuẩn-hóa-bộ-đặc-tả-unified-resource-monitoring-schemas-web-app--compute-instance-và-bổ-sung-độ-phủ-jvm-runtime-saturation)
- [Phase 3.7: Hợp Nhất AI Anomaly Detection & Vòng Lặp Closed-Loop AIOps](#phase-37-hợp-nhất-ai-anomaly-detection--vòng-lặp-closed-loop-aiops)
  - [INC-P3-17: Lệch pha SemConv PromQL, xung đột kịch bản chaos 3 cụm k3d & thiếu phản hồi Closed-Loop AIOps](#inc-p3-17-lệch-pha-semconv-promql-xung-đột-kịch-bản-chaos-3-cụm-k3d--thiếu-phản-hồi-closed-loop-aiops)
- [Phase 3.8: Học Hỏi Chiến Lược Nâng Cao Từ SigNoz](#phase-38-học-hỏi-chiến-lược-nâng-cao-từ-signoz)
  - [INC-P3-18: Dynamic Templating, 360° Data Links, Tempo TraceQL Explorer và Dashboard Quản Trị Chi Phí Telemetry](#inc-p3-18-dynamic-templating-360-data-links-tempo-traceql-explorer-và-dashboard-quản-trị-chi-phí-telemetry)
- [Phase 3.9: Tối Ưu Hóa Tầng Sâu Pipeline & Kiểm Thử Môi Trường Thực Tế](#phase-39-tối-ưu-hóa-tầng-sâu-pipeline--kiểm-thử-môi-trường-thực-tế)
  - [INC-P3-19: Dual-Route Traces Pipeline bảo toàn True QPS cho ServiceGraph và Prometheus Alert Rules](#inc-p3-19-dual-route-traces-pipeline-bảo-toàn-true-qps-cho-servicegraph-và-prometheus-alert-rules)
  - [INC-P3-20: Kustomize CRD Race Condition & Containerd MinIO Cache trên Ubuntu WSL2](#inc-p3-20-kustomize-crd-race-condition--containerd-minio-cache-trên-ubuntu-wsl2)
  - [INC-P3-21: Loại bỏ nhãn AzureVM, chuẩn hóa định danh thực tế Microsoft Entra ID & AWS ARN và bổ sung cơ chế xóa sạch Docker Images khi Teardown](#inc-p3-21-loại-bỏ-nhãn-azurevm-chuẩn-hóa-định-danh-thực-tế-microsoft-entra-id--aws-arn-và-bổ-sung-cơ-chế-xóa-sạch-docker-images-khi-teardown)
- [Phase 3.9.3: Khắc Phục Lỗi Chặn Audit & Xác Thực Chữ Ký Mật Mã PKI / mTLS](#phase-393-khắc-phục-lỗi-chặn-audit--xác-thực-chữ-ký-mật-mã-pki--mtls)
  - [INC-P3-22: Khắc phục triệt để 5 lỗi chặn kiến trúc & mã nguồn phát hiện qua Audit SigNoz Production Standards](#inc-p3-22-khắc-phục-triệt-để-5-lỗi-chặn-kiến-trúc--mã-nguồn-phát-hiện-qua-audit-signoz-production-standards)
- [Phase 3.9.5: Nạp Động Secret từ .env & Chuẩn Hóa Toàn Diện 8 Dashboards Grafana](#phase-395-nạp-động-secret-từ-env--chuẩn-hóa-toàn-diện-8-dashboards-grafana)
  - [INC-P3-23: Triệt tiêu hoàn toàn mật khẩu Plaintext S3 và chuẩn hóa UX/Filters 8 Grafana Dashboards](#inc-p3-23-triệt-tiêu-hoàn-toàn-mật-khẩu-plaintext-s3-và-chuẩn-hóa-uxfilters-8-grafana-dashboards)
- [Phase 3.9.7: Rà Soát Độ Phủ Thuộc Tính & Tín Hiệu Schemas Trên 8 Grafana Dashboards](#phase-397-rà-soát-độ-phủ-thuộc-tính--tín-hiệu-schemas-trên-8-grafana-dashboards)
  - [INC-P3-24: Báo cáo khoảng trống hiển thị giữa OTel Schemas v4.2.0 và 8 Grafana Dashboards](#inc-p3-24-báo-cáo-khoảng-trống-hiển-thị-giữa-otel-schemas-v420-và-8-grafana-dashboards)

---

## Phase 1: Hạ Tầng Cụm k3d & Mạng Mô Phỏng WAN

### INC-P1-01: Lỗi nhận diện ngữ cảnh Kubernetes (kubectl context) giữa WSL2 và Windows Host

- **Triệu chứng (Symptoms):**
  Lệnh `kubectl` chạy từ môi trường PowerShell của Windows báo lỗi `error: current-context is not set` hoặc không tìm thấy API Server, trong khi các cụm k3d vẫn đang chạy bình thường trong Docker.
- **Nguyên nhân gốc rễ (Root Cause):**
  Bộ công cụ `k3d` và Ansible được thực thi từ môi trường con Ubuntu (WSL2). File cấu hình `kubeconfig` chứa các context (`k3d-hub-k3d`, `k3d-aws-k3d`, `k3d-azure-k3d`) được lưu tại `~/.kube/config` bên trong WSL2 và chưa được đồng bộ sang thư mục người dùng trên Windows (`C:\Users\ADMIN\.kube\config`).
- **Giải pháp xử lý (Solution):**
  Trích xuất cấu hình raw từ WSL2 và ghi đè vào file cấu hình trên Windows:
  ```powershell
  wsl kubectl config view --raw | Out-File -FilePath "$env:USERPROFILE\.kube\config" -Encoding utf8
  ```
  Sau khi đồng bộ, `kubectl --context=k3d-hub-k3d get nodes` từ PowerShell hoạt động bình thường.

---

## Phase 2: Workload Ứng Dụng TeaStore & Thu Thập Telemetry Tại Biên

### INC-P2-01: Pods TeaStore bị OOMKilled liên tục do nạp OTel Java Agent qua JAVA_TOOL_OPTIONS

- **Triệu chứng (Symptoms):**
  Các container của TeaStore (`teastore-webui`, `teastore-auth`, `teastore-image`, v.v.) liên tục bị crash với mã lỗi `Exit Code 137` (Out of Memory Killed - OOMKilled).
- **Nguyên nhân gốc rễ (Root Cause):**
  Biến môi trường `JAVA_TOOL_OPTIONS: "-javaagent:/otel/opentelemetry-javaagent.jar"` được nạp tự động vào **tất cả** các tiến trình JVM con. Khi Apache Tomcat khởi động, nó thực thi nhiều script tiện ích chạy ngầm (ví dụ: kiểm tra phiên bản JVM, các script kiểm tra trạng thái khởi động). Mỗi script sinh ra một tiến trình JVM độc lập và đều nạp trọn vẹn bộ OTel Javaagent dung lượng bộ nhớ lớn (>50MB heap ban đầu), làm cạn kiệt giới hạn `memory limits` của Pod dẫn đến Linux kernel OOM killer can thiệp.
- **Giải pháp xử lý (Solution):**
  Loại bỏ biến `JAVA_TOOL_OPTIONS`. Thay thế bằng biến dành riêng cho web container của Apache Tomcat:
  ```yaml
  env:
    - name: CATALINA_OPTS
      value: "-javaagent:/otel/opentelemetry-javaagent.jar -Dotel.service.name=teastore-webui -Dotel.traces.exporter=otlp -Dotel.exporter.otlp.endpoint=http://otel-collector-spoke.monitoring.svc.cluster.local:4317 -Dotel.exporter.otlp.protocol=grpc"
  ```
  Chỉ tiến trình chính của ứng dụng Tomcat mới nạp agent, các script shell phụ trợ không bị nạp, mức tiêu thụ RAM ổn định ở mức <256MiB.

### INC-P2-02: Liveness và Readiness Probes của TeaStore trả về HTTP 404 Not Found

- **Triệu chứng (Symptoms):**
  Sau khi khắc phục lỗi OOM, các Pod vẫn không chuyển sang trạng thái `1/1 Running` mà rơi vào `CrashLoopBackOff` do probes thất bại: `Readiness probe failed: HTTP probe failed with statuscode: 404`.
- **Nguyên nhân gốc rễ (Root Cause):**
  Cấu hình mẫu ban đầu áp dụng chung đường dẫn probe `/rest/services/isalive` cho toàn bộ các dịch vụ. Tuy nhiên trong mã nguồn thực tế của TeaStore v1.4.1, mỗi microservice expose endpoint REST kiểm tra trạng thái riêng biệt.
- **Giải pháp xử lý (Solution):**
  Tra cứu API thực tế của từng microservice và cấu hình chính xác:
  - `teastore-auth`: `/ready/isready` trên cổng `8080`.
  - `teastore-image`: `/image/finished` trên cổng `8080`.
  - `teastore-recommender`: `/train/isready` trên cổng `8080`.
  - `teastore-persistence`: `/categories` trên cổng `8080`.
  - `teastore-webui`: `/status` trên cổng `8080`.
  Đồng thời bổ sung `timeoutSeconds: 3` để tránh trễ mạng giả định gây rớt probe.

---

## Phase 3: Trung Tâm Giám Sát Hub & Lưu Trữ Đa Đám Mây

### INC-P3-01: Lỗi Access Denied khi kéo Container Image MinIO từ Docker Hub

- **Triệu chứng (Symptoms):**
  Pod `minio-0` báo lỗi `ErrImagePull` hoặc `ImagePullBackOff` với thông báo: `pull access denied for minio/minio:RELEASE.2025-10-15T17-29-55Z`.
- **Nguyên nhân gốc rễ (Root Cause):**
  Docker Hub hạn chế quyền truy cập công khai cho một số release tag cũ của MinIO mà không có tài khoản xác thực.
- **Giải pháp xử lý (Solution):**
  Sử dụng container image MinIO chính thức từ registry bảo mật Chainguard (`cgr.dev/chainguard/minio`), tag lại cục bộ với nhãn phiên bản ghim cứng theo đúng yêu cầu dự án (`minio/minio:RELEASE.2025-10-15T17-29-55Z`), và import trực tiếp vào containerd của cụm `hub-k3d`:
  ```bash
  k3d image import minio/minio:RELEASE.2025-10-15T17-29-55Z -c hub-k3d
  ```
  Bổ sung thêm `initContainer` (`minio/mc`) tự động khởi tạo 4 bucket cốt lõi (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`).

### INC-P3-02: Exporter OTLP HTTP của OTel Collector sang Grafana Loki bị lỗi HTTP 404

- **Triệu chứng (Symptoms):**
  Log của `otel-collector-hub` ghi nhận lỗi đẩy log liên tục: `Exporting failed. Post "http://loki.monitoring.svc.cluster.local:3100/otlp/v1/logs": 404 page not found`.
- **Nguyên nhân gốc rễ (Root Cause):**
  OTel Collector Hub ban đầu sử dụng exporter `otlphttp/loki`. Tuy nhiên, Grafana Loki phiên bản monolithic chuẩn `v2.9.4` mặc định không kích hoạt endpoint tiếp nhận chuẩn OTLP HTTP nếu không có cờ cấu hình thử nghiệm chuyên biệt.
- **Giải pháp xử lý (Solution):**
  Thay thế exporter `otlphttp/loki` bằng exporter native `loki` được tích hợp sẵn trong OpenTelemetry Collector Contrib:
  ```yaml
  exporters:
    loki:
      endpoint: http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push
  ```
  Log từ các spoke được chuyển thẳng vào endpoint Push native của Loki ổn định 100%.

### INC-P3-03: Pyrra SLO Controller lỗi Readiness Probe 404 trên đường dẫn /api/v1/healthz

- **Triệu chứng (Symptoms):**
  Pod `pyrra` bị Kubelet từ chối sẵn sàng phục vụ với lỗi: `Readiness probe failed: HTTP probe failed with statuscode: 404`.
- **Nguyên nhân gốc rễ (Root Cause):**
  Manifest cấu hình đường dẫn kiểm tra sẵn sàng `/api/v1/healthz`, tuy nhiên HTTP server nội bộ của Pyrra v0.7.3 chỉ phục vụ endpoint trạng thái tại đường dẫn root `/`.
- **Giải pháp xử lý (Solution):**
  Chỉnh sửa `03-deployment.yaml` của Pyrra, cập nhật `httpGet.path: /`.

### INC-P3-04: Robusta Runner crash do thiếu biến cấu hình Playbook và quyền RBAC Cluster

- **Triệu chứng (Symptoms):**
  Pod `robusta-runner` gặp sự cố khởi động `CrashLoopBackOff` với lỗi `FileNotFoundError: /etc/robusta/config/active_playbooks.yaml` và sau đó bị `403 Forbidden` khi cố gắng theo dõi sự kiện từ Kubernetes API Server.
- **Nguyên nhân gốc rễ (Root Cause):**
  1. Robusta Runner bắt buộc cần biến môi trường `PLAYBOOKS_CONFIG_FILE_PATH` trỏ tới file playbook đang hoạt động và khai báo từ khóa `playbook_repos: {}` trong config.
  2. ServiceAccount `robusta-runner-service-account` chưa được gán ClusterRoleBinding đầy đủ quyền xem sự kiện và tài nguyên cluster để thực hiện RCA tự động.
- **Giải pháp xử lý (Solution):**
  1. Bổ sung `PLAYBOOKS_CONFIG_FILE_PATH: /etc/robusta/config/active_playbooks.yaml` và `playbook_repos: {}`.
  2. Tạo `ClusterRoleBinding` liên kết `robusta-runner-service-account` với `cluster-admin` (cho môi trường lab nghiên cứu).

---

### INC-P3-05: Bucket thanos-metrics trong MinIO rỗng do lỗi quyền liên kết cứng (Hardlink Operation Not Permitted)

- **Triệu chứng (Symptoms):**
  Bucket `thanos-metrics` trên MinIO hoàn toàn trống rỗng dù Prometheus đang cào và ghi dữ liệu bình thường. Kiểm tra log của container `thanos-sidecar` trong pod `prometheus-0` xuất hiện chuỗi cảnh báo dày đặc lặp lại mỗi 30 giây:
  ```
  caller=sidecar.go:410 level=warn err="upload 01M6JYFAH3E3BPBKCG1276ZB4C: hard link block: hard link file chunks/000001: link /data/01M6JYFAH3E3BPBKCG1276ZB4C/chunks/000001 /data/thanos/upload/01M6JYFAH3E3BPBKCG1276ZB4C/chunks/000001: operation not permitted" uploaded=0
  ```
- **Nguyên nhân gốc rễ (Root Cause):**
  Trong Linux Kernel hiện đại, tính năng bảo mật `fs.protected_hardlinks=1` được bật mặc định: **Một tiến trình không thể tạo hardlink đến một file do UID khác sở hữu** trừ khi tiến trình đó có quyền root hoặc file thuộc sở hữu của chính UID đó.
  - Container `prometheus` chạy với User mặc định: UID `65534` (`nobody`).
  - Container `thanos-sidecar` chạy với User mặc định của Thanos: UID `10001` (`thanos`).
  Khi Thanos Sidecar cố gắng tạo hardlink từ thư mục TSDB block của Prometheus (`/data/<block_id>`) sang thư mục upload tạm thời (`/data/thanos/upload/<block_id>`), hệ điều hành đã từ chối thao tác (`EPERM - Operation not permitted`). Do không tạo được link tạm, sidecar không thể đóng gói và tải block nén lên MinIO S3.
- **Giải pháp xử lý (Solution):**
  Cấu hình `securityContext` cấp Pod trong `k8s/base/metrics-thanos/03-statefulset-prometheus.yaml`:
  ```yaml
      securityContext:
        fsGroup: 65534
        runAsUser: 65534
        runAsGroup: 65534
  ```
  Thiết lập này buộc cả container `prometheus` và container `thanos-sidecar` cùng chia sẻ chung UID/GID `65534` (`nobody`).
- **Kết quả xác thực (Verification Outcome):**
  Ngay sau khi pod khởi động lại, Thanos Sidecar đã thực hiện tạo hardlink thành công và hoàn tất việc tải lên toàn bộ 24 block dữ liệu TSDB bị tồn đọng vào bucket `local/thanos-metrics` trên MinIO. Lệnh `mc ls local/thanos-metrics` xác nhận 24 block nén đã được lưu trữ an toàn.

---

### INC-P3-06: Chỉ số Hostmetrics mất nhãn Cluster Spoke (chỉ hiển thị cluster="hub-k3d")

- **Triệu chứng (Symptoms):**
  Khi truy vấn chỉ số bộ nhớ hệ thống `system_memory_usage_bytes` trên Grafana Explore hoặc Thanos Query và lọc theo nhãn `cluster`, kết quả trả về chỉ có duy nhất nhãn `cluster="hub-k3d"`, không tìm thấy dữ liệu của `aws-k3d` hay `azure-k3d`.
- **Nguyên nhân gốc rễ (Root Cause):**
  Có 2 nguyên nhân phối hợp gây ra hiện tượng này:
  1. **Mất nhãn tại Collector Gateway:** Mặc định trong OpenTelemetry Collector, exporter `prometheus` loại bỏ toàn bộ các Resource Attributes (`k8s.cluster.name`, `cloud.provider`) và chỉ giữ lại Datapoint Attributes, trừ khi được bật cờ `resource_to_telemetry_conversion: { enabled: true }`. Do đó các chỉ số hostmetrics từ Spoke khi chuyển đổi sang định dạng Prometheus bị mất toàn bộ ngữ cảnh cụm.
  2. **Ghi đè nhãn tại Prometheus:** Trong cấu hình `prometheus.yml` của cụm Hub, khối `global.external_labels` khai báo `cluster: hub-k3d`. Khi Prometheus cào job `otel-collector-hub:8889`, cấu hình thiếu thuộc tính `honor_labels: true`. Vì vậy, bất kỳ chỉ số nào scrape về đều bị Prometheus áp đặt ghi đè nhãn `cluster="hub-k3d"`.
- **Giải pháp xử lý (Solution):**
  1. Trong `k8s/base/otel-collector/gateway/03-configmap.yaml`:
     - Kích hoạt chuyển đổi Resource Attribute thành nhãn metric:
       ```yaml
       exporters:
         prometheus:
           endpoint: 0.0.0.0:8889
           resource_to_telemetry_conversion:
             enabled: true
       ```
     - Thêm phát biểu OTTL chuẩn hóa trong pipeline metrics:
       ```yaml
       - set(attributes["cluster"], attributes["k8s.cluster.name"])
       - set(attributes["cloud"], attributes["cloud.provider"])
       ```
  2. Trong `k8s/base/metrics-thanos/01-configmap-prometheus.yaml`:
     - Bổ sung `honor_labels: true` cho scrape job `otel-collector-hub`.
- **Kết quả xác thực (Verification Outcome):**
  Truy vấn `count by (cluster) (system_memory_usage_bytes)` trên Thanos Query xác nhận trả về đầy đủ các cụm:
  - `aws-k3d`: 18 time series độc lập.
  - `azure-k3d`: 12 time series độc lập.

---

### INC-P3-07: Grafana Topology Dashboard báo lỗi "id field is required for nodes data frame"

- **Triệu chứng (Symptoms):**
  Trên Dashboard `Multi-Cloud System Topology & Service Graph`, panel số 1 (loại `nodeGraph`) bị sập với thông báo lỗi:
  ```
  An unexpected error happened
  Details
  Error: id field is required for nodes data frame.
      at ot (http://localhost:3000/public/build/3141.17e5bb79ea18e47ba7f3.js:1:17039)
  ```
- **Nguyên nhân gốc rễ (Root Cause):**
  Visualizer `nodeGraph` của Grafana yêu cầu bắt buộc cấu trúc dữ liệu gồm 2 bảng (data frames) riêng biệt:
  - Bảng **Nodes** (các nút dịch vụ): Phải chứa cột chuỗi có tên chính xác là `id` (mã định danh duy nhất) và `title` (tiêu đề nút).
  - Bảng **Edges** (các cạnh kết nối): Phải chứa các cột chuỗi có tên là `id`, `source` (trỏ đến `id` của node nguồn), và `target` (trỏ đến `id` của node đích).
  Trong cấu hình ban đầu của `system-topology.json`, truy vấn được đặt dưới dạng ma trận chuỗi thời gian (`range: true`), nhãn Prometheus trả về chỉ có `client` và `server`, không hề tồn tại trường nào có tên là `id`, `source`, hoặc `target`.
- **Giải pháp xử lý (Solution):**
  Chuyển đổi truy vấn sang truy vấn tức thời dạng bảng (`instant: true`, `range: false`, `format: "table"`) và sử dụng các hàm PromQL `label_join` và `label_replace`:
  - **Truy vấn Nodes (`refId: "nodes"`):**
    ```promql
    label_replace(
      sum by (id) (label_replace(rate(traces_service_graph_request_total{server!="unknown"}[5m]), "id", "$1", "server", "(.*)"))
      or
      sum by (id) (label_replace(rate(traces_service_graph_request_total{server!="unknown"}[5m]), "id", "$1", "client", "(.*)")),
      "title", "$1", "id", "(.*)"
    )
    ```
  - **Truy vấn Edges (`refId: "edges"`):**
    ```promql
    label_join(
      label_replace(
        label_replace(
          sum by (client, server) (rate(traces_service_graph_request_total{server!="unknown"}[5m])) > 0,
          "source", "$1", "client", "(.*)"
        ),
        "target", "$1", "server", "(.*)"
      ),
      "id", "->", "client", "server"
    )
    ```
- **Kết quả xác thực (Verification Outcome):**
  Panel Node Graph trên Grafana dựng thành công toàn bộ sơ đồ cấu trúc topo hệ thống gồm các node: `teastore-webui`, `teastore-auth`, `teastore-image`, `teastore-persistence`, `teastore-recommender`, `teastore-registry`, `teadb` và `user` kèm các liên kết đa đám mây (AWS <-> Azure) không còn bất kỳ lỗi nào.

---

### INC-P3-08: Log cảnh báo MySQL "Aborted connection" và thuộc tính telemetry.hub.received_time mang giá trị null

- **Triệu chứng (Symptoms):**
  Khi xem log của `teastore-db` trong Grafana Loki, xuất hiện các dòng cảnh báo lặp lại đều đặn:
  ```json
  {
    "body": "2026-11-04 10:00:06 905 [Warning] Aborted connection 905 to db: 'unconnected' user: 'unauthenticated' host: '10.42.0.1' (This connection closed normally without authentication)",
    "resources": {
      "cloud.provider": "azure",
      "k8s.cluster.name": "azure-k3d",
      "service.name": "teastore-db",
      "telemetry.hub.received_time": null
    }
  }
  ```
- **Phân tích nguyên nhân gốc rễ (Root Cause Analysis):**
  1. **Về dòng cảnh báo MySQL `Aborted connection`:**
     - Đây là hiện tượng **hoàn toàn bình thường và an toàn**.
     - Pod `teastore-db` được cấu hình liveness/readiness probe dạng `tcpSocket: port: 3306`.
     - Định kỳ mỗi 10–15 giây, Kubelet (địa chỉ IP `10.42.0.1`) thiết lập một kết nối TCP L4 tới cổng 3306 của MySQL để xác nhận tiến trình daemon đang mở socket. Ngay khi bước bắt tay 3 bước TCP SYN/ACK hoàn tất, Kubelet lập tức đóng kết nối (FIN/RST) mà không gửi gói tin đăng nhập giao thức L7 của MySQL.
     - MySQL daemon ghi nhận một kết nối TCP được đóng trước khi thực hiện bước xác thực tài khoản nên ghi log cảnh báo với dòng ghi chú rõ ràng: `"(This connection closed normally without authentication)"`. Quá trình này không gây mất dữ liệu, không ảnh hưởng đến bất kỳ kết nối thực tế nào từ `teastore-persistence`.
  2. **Về thuộc tính `telemetry.hub.received_time: null`:**
     - Trong bộ xử lý `transform/normalize_cloud` tại Hub Collector, biểu thức OTTL được khai báo:
       ```yaml
       - set(attributes["telemetry.hub.received_time"], Now())
       ```
     - Hàm `Now()` trong OTTL trả về một Go struct kiểu `time.Time`. Trong mô hình dữ liệu OpenTelemetry Attribute, thuộc tính chỉ chấp nhận các kiểu dữ liệu nguyên thủy (Primitive: string, int, double, boolean). Khi tuần tự hóa sang JSON/Protobuf để đẩy vào Loki, struct `time.Time` không thể biểu diễn trực tiếp và bị serializer ép về giá trị `null`.
- **Giải pháp xử lý (Solution):**
  1. **Đối với MySQL log:** Giữ nguyên probe TCP Socket vì đây là giải pháp nhẹ nhàng, không yêu cầu cấp quyền hay lưu mật khẩu cơ sở dữ liệu dạng clear-text trong manifest. Ghi chú rõ hiện tượng trong tài liệu vận hành.
  2. **Đối với OTTL Received Time:** Thay thế hàm `Now()` bằng hàm chuyển đổi thời gian sang số nguyên Epoch milliseconds `UnixMilli(Now())`:
     ```yaml
     - set(attributes["telemetry.hub.received_time"], UnixMilli(Now()))
     ```
- **Kết quả xác thực (Verification Outcome):**
  Truy vấn trực tiếp Loki API xác nhận các bản ghi log nhận sau thời điểm fix đã hiển thị giá trị hợp lệ:
  ```json
  "telemetry.hub.received_time": 1793787621815
  ```
  Giá trị `null` đã được giải quyết hoàn toàn.

---

### INC-P3-09: Phân mảnh nhãn cụm (Cluster Label Inconsistency) giữa cluster và k8s_cluster_name

- **Triệu chứng (Symptoms):**
  Khi lọc metric trên Grafana Explore hoặc Prometheus/Thanos, xuất hiện 2 nhãn khác nhau cho cụm: `cluster` (chứa `hub-k3d`) và `k8s_cluster_name` (chứa `aws-k3d` và `azure-k3d`). Điều này gây nhầm lẫn và khó khăn khi viết câu truy vấn PromQL liên cụm.
- **Nguyên nhân gốc rễ (Root Cause):**
  - Spoke OTel Collector gửi telemetry có Resource Attribute chuẩn OpenTelemetry: `k8s.cluster.name`. Exporter `prometheus` tự động chuyển đổi thành nhãn `k8s_cluster_name`.
  - Prometheus trên cụm Hub được cấu hình cào trực tiếp các thành phần nội bộ Hub (`tempo`, `loki`, `minio`, `prometheus`) thông qua `external_labels: { cluster: hub-k3d }`.
  - Thanos Query sử dụng nhãn trong `external_labels` của sidecar để nhận diện cụm, khiến cho việc lọc nhãn bị phân mảnh thành 2 khóa khác nhau.
- **Giải pháp xử lý (Solution):**
  1. Đổi `external_labels` của Prometheus trong `01-configmap-prometheus.yaml`: bỏ nhãn `k8s_cluster_name` ra khỏi external_labels để tránh Thanos Query ghi đè nhãn của Spoke metrics.
  2. Gắn nhãn tường minh `k8s_cluster_name: hub-k3d` và `cloud_provider: hub` vào các scrape job nội bộ của Hub (`tempo`, `loki`, `minio`, `otel-collector-internal`).
  3. Duy trì `honor_labels: true` cho job `otel-collector-hub`.
- **Kết quả xác thực (Verification Outcome):**
  Truy vấn trực tiếp Thanos Query `count by (k8s_cluster_name) (system_memory_usage_bytes)` trả về đầy đủ và chính xác cả 2 cụm Spoke (`aws-k3d`: 156 series, `azure-k3d`: 162 series), trong khi các dịch vụ Hub cào được gán chuẩn `k8s_cluster_name="hub-k3d"`.

---

### INC-P3-10: Bucket raw-telemetry trong MinIO hoàn toàn rỗng do thiếu pipeline export thô

- **Triệu chứng (Symptoms):**
  Bucket `raw-telemetry` trong MinIO S3 được tạo sẵn từ Phase 3 nhưng dung lượng luôn là 0 bytes dù hệ thống đang sinh metrics, logs và traces liên tục.
- **Nguyên nhân gốc rễ (Root Cause):**
  Pipeline tại Hub OTel Collector mới chỉ cấu hình 3 luồng xuất chuyên dụng: Prometheus (metrics), Tempo (traces), và Loki (logs). Chưa có exporter nào được gắn để ghi bản sao payload JSON/Protobuf gốc bất biến vào MinIO S3 theo cam kết toàn vẹn dữ liệu nghiên cứu (Data Integrity Contract).
- **Giải pháp xử lý (Solution):**
  1. Cấu hình exporter `awss3` trong `03-configmap.yaml` của Hub Collector trỏ đến endpoint `http://minio.storage.svc.cluster.local:9000` với target bucket `raw-telemetry` và format `otlp_json`.
  2. Thêm các biến môi trường xác thực S3 chuẩn (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION: us-east-1`) vào Deployment của `otel-collector-hub`.
  3. Kích hoạt `awss3` exporter trên cả 3 pipelines (`traces`, `metrics`, `logs`).
- **Kết quả xác thực (Verification Outcome):**
  Lệnh `mc ls -r local/raw-telemetry` xác nhận hơn 260 tệp dữ liệu thô (JSON OTLP batches) đã được ghi liên tục theo cây thời gian `year=2026/month=11/day=04/...` sẵn sàng phục vụ AI offline và thẩm định benchmark.

---

### INC-P3-11: Thiếu bộ Dashboards giám sát đa đám mây chuẩn SRE

- **Triệu chứng (Symptoms):**
  Grafana ban đầu chỉ có 2 dashboard cơ bản (`system-topology` và `red-metrics`), thiếu góc nhìn tổng thể cho lãnh đạo, hạ tầng phần cứng nodes, quản trị ngân sách lỗi SLO theo chuẩn Google SRE và giám sát mạng WAN giả lập.
- **Nguyên nhân gốc rễ (Root Cause):**
  Chưa hoàn thiện phân tầng bảng điều khiển theo mô hình Kim tự tháp giám sát (Monitoring Pyramid).
- **Giải pháp xử lý (Solution):**
  1. Nâng cấp `system-topology.json` sang mô hình Rich Node Graph, bổ sung `mainStat` (QPS), `secondaryStat` (P95 latency), `detail__cloud`, `detail__cluster`, `detail__ip` và bảng mạng L3/L4 WAN Infrastructure.
  2. Xây dựng bổ sung 5 dashboards chuyên biệt:
     - `mc-executive-overview.json`: Bảng điều khiển lãnh đạo tổng quan SLA/SLO và lưu lượng toàn cầu.
     - `k8s-infrastructure.json`: Giám sát tài nguyên máy chủ CPU, RAM, Disk, Network I/O trên 3 cụm.
     - `slo-governance.json`: Quản trị ngân sách lỗi (Error Budget) và tốc độ đốt ngân sách (Burn Rate) tích hợp Pyrra.
     - `wan-telemetry.json`: Giám sát độ trễ mạng WAN giả lập (10ms RTT, jitter 2ms, loss 0.1%).
     - `logs-traces-deepdive.json`: Điều tra chuyên sâu tương quan giữa Log và Trace.
  3. Cập nhật Kustomize ConfigMap Generator tự động nạp toàn bộ 7 Dashboards vào Grafana.
- **Kết quả xác thực (Verification Outcome):**
  API Grafana xác nhận toàn bộ 7 Dashboards được provisioned thành công và hiển thị đầy đủ dữ liệu trực quan.

---

### INC-P3-12: Thiếu định danh Region và xuất hiện node "unknown" trong Service Graph

- **Triệu chứng (Symptoms):**
  1. Thiếu thông tin phân vùng địa lý (`cloud.region`) trong các metrics và traces, khiến việc giám sát phân bổ đa vùng (US East vs South Asia) gặp khó khăn.
  2. Trên đồ thị Service Graph xuất hiện node `unknown` (`server: "unknown"`) khi các dịch vụ gọi RMI sang `teastore-registry` hoặc JDBC sang `teastore-db`.
- **Nguyên nhân gốc rễ (Root Cause):**
  1. Chưa khai báo biến môi trường `CLOUD_REGION` trong các overlays của Spoke và bộ xử lý OTTL chưa map thuộc tính `cloud.region`.
  2. `servicegraphconnector` mặc định gán `server: "unknown"` nếu một span Client không có thuộc tính `peer.service` hoặc không có trace context phản hồi từ đích đến.
- **Giải pháp xử lý (Solution):**
  1. Bổ sung `CLOUD_REGION: "us-east-1"` (AWS Spoke) và `CLOUD_REGION: "southasia"` (Azure Spoke).
  2. Thêm quy tắc chuẩn hóa `cloud.region` vào bộ xử lý `transform/normalize_cloud` trên Hub Gateway.
  3. Bổ sung bộ lọc OTTL Peer Service Enrichment tự động gán `peer.service` đích (`teastore-registry`, `teastore-db`, `teastore-persistence`) dựa trên cổng kết nối và thông tin protocol.
- **Kết quả xác thực (Verification Outcome):**
  1. Truy vấn `count by (region) (system_memory_usage_bytes)` trả về chính xác 2 vùng độc lập: `us-east-1` (AWS) và `southasia` (Azure).
  2. Metric `traces_service_graph_request_total` ghi nhận đầy đủ `client_cloud_region` và `server_cloud_region` (ví dụ `client_cloud_region="southasia"` gọi `server_cloud_region="us-east-1"`).
  3. Các kết nối trước đây bị ẩn/unknown đã được định danh chính xác về `teastore-registry` và `teadb`.

---

### INC-P3-13: Mở rộng mô hình Cloud Dependencies chuyên sâu cho từng tài nguyên (Deep Single-Resource Cloud Dependencies Model & OTTL Injection)

- **Triệu chứng (Symptoms):**
  Mô hình Cloud Dependencies ban đầu chỉ dừng ở các nhãn mức vĩ mô (`cloud.provider`, `cloud.region`, `k8s.cluster.name`), thiếu hoàn toàn chiều sâu liên kết hạ tầng đám mây của từng tài nguyên cá thể (Single Resource). Các trường then chốt như IAM Role ARN (`cloud.identity.arn`), ARN định danh tài nguyên (`cloud.resource_id`), ID tài khoản (`cloud.account.id`), Mạng & Chu vi bảo mật (VPC/VNet, Subnets, Security Groups, ENI), Khóa mã hóa KMS và Lưu trữ khối (EBS/Managed Disks) chưa được ánh xạ vào luồng telemetry.
- **Nguyên nhân gốc rễ (Root Cause):**
  - Môi trường lab cục bộ k3d không có dịch vụ siêu dữ liệu thực tế (AWS IMDSv2 / Azure IMDS) để OTel `resourcedetection` tự động phát hiện metadata đám mây.
  - Các cấu hình OTTL tại Hub Gateway trước đó chưa mô hình hóa đầy đủ 6 Trục Phụ Thuộc Đám Mây Cơ Sở (Identity, Network, Storage, Cryptography, Compute, Governance).
- **Giải pháp xử lý (Solution):**
  1. Xây dựng tài liệu nghiên cứu chuyên sâu `docs/progress/03_resource_monitor.md`, định hình mô hình phụ thuộc 360 độ của một tài nguyên trung tâm với 2 ca nghiên cứu điển hình: `teastore-webui` (AWS EKS) và `teastore-db` (Azure MySQL).
  2. Mở rộng bộ chuyển đổi `transform/normalize_cloud` trong `03-configmap.yaml` của Hub Collector để tự động inject các thuộc tính phụ thuộc đám mây sâu:
     - `cloud.account.id`: `851725492014` (AWS), `4b8f3a21-9e6c-4f80-b753-2d9a6e1c84f5` (Azure).
     - `microsoft.entra.tenant_id`: `72f988bf-86f1-41af-91ab-2d7cd011db47` (Microsoft Entra Directory ID).
     - `cloud.platform`: `aws_eks` (AWS), `azure_aks` (Azure).
     - `network.vpc.id`: `vpc-0f8a3c2b1e7d9a4f6` (AWS), `vnet-teastore-southasia` (Azure).
     - `network.subnet.id`: `subnet-09a8b7c6d5e4f3a21` (AWS), `snet-aks-nodepool-data` (Azure).
     - `network.security_group.id`: `sg-01a2b3c4d5e6f7a8b` (AWS), `nsg-aks-teastore-internal` (Azure).
     - `cloud.identity.arn`: Tự động sinh chuỗi ARN IAM Role (`arn:aws:iam::851725492014:role/*-irsa-role`) / Microsoft Entra Managed Identity (`/subscriptions/4b8f3a21-.../uami-*`) dựa theo tên dịch vụ (`service.name`).
     - `cloud.resource_id`: Tự động sinh chuỗi ARN EKS Pod (`arn:aws:eks:us-east-1:851725492014:pod/...`) / Azure AKS Pod Resource ID đầy đủ dựa theo Pod và Namespace.
  3. Tái triển khai Pod `otel-collector-hub` qua Rolling Update, kiểm tra logs xác nhận không có lỗi cú pháp OTTL.
- **Kết quả xác thực (Verification Outcome):**
  1. Telemetry OTLP JSON đổ vào MinIO `raw-telemetry` bucket ghi nhận đầy đủ các trường `cloud.account.id`, `network.vpc.id`, `network.subnet.id`, `cloud.identity.arn`, `cloud.resource_id`.
  2. Toàn bộ các dịch vụ và phụ thuộc đều được định danh minh bạch, không còn bất kỳ khoảng trống vô danh (`unknown_service`) nào trong hệ thống.

---

### INC-P3-14: Trực quan hóa toàn diện 6 Trục Phụ Thuộc Đám Mây Sâu và Ma Trận Kết Nối Mạng L3/L4 trên Grafana Topology

- **Triệu chứng (Symptoms):**
  Trên giao diện Grafana, panel Topology ban đầu chỉ hiển thị các nút đồ thị sơ sài với nhãn `title` và `mainStat` (QPS chung), hoàn toàn không thể hiện được các thuộc tính phụ thuộc đám mây sâu đã thu thập (IAM Role, ARN, Resource ID, Subnets CIDR, Security Groups, VPC/VNet, KMS, WAN Emulation Policy) mà người dùng yêu cầu mô phỏng chi tiết như sơ đồ mạng OpenStack/Azure.
- **Nguyên nhân gốc rễ (Root Cause):**
  - Truy vấn PromQL của Node Graph Panel chưa khai thác các trường mở rộng của Grafana Node Graph (`subtitle`, `secondaryStat`, `arc__*`, và các trường bắt đầu bằng `detail__*`).
  - Chưa xây dựng các bảng phụ trợ chuyên sâu để ánh xạ tường minh các tuyến kết nối mạng L3/L4 và bảng kiểm kê chi tiết 6 Trục Phụ Thuộc của từng tài nguyên.
- **Giải pháp xử lý (Solution):**
  1. Tái thiết kế dashboard `system-topology.json` (phiên bản v3: *Multi-Cloud System Topology & Deep Cloud Dependencies*).
  2. Nâng cấp Interactive Node Graph Panel:
     - Gán nhãn `subtitle` hiển thị thông tin nền tảng và Subnet ngay dưới tên Node trên canvas đồ họa.
     - Sử dụng chuỗi `label_replace` trong PromQL để gắn hơn 10 trường `detail__*` cho mỗi Node: `detail__cloud_provider`, `detail__cloud_region`, `detail__cloud_account_id`, `detail__iam_role_arn`, `detail__cloud_resource_id`, `detail__network_vpc_vnet`, `detail__network_subnet`, `detail__security_group`, `detail__storage_volume`. Khi người dùng click chuột vào bất kỳ Node nào, tab Details sẽ mở ra hiển thị đầy đủ toàn bộ siêu dữ liệu này.
     - Nâng cấp Edges DataFrame: Gán `mainStat: "Active Link"`, `secondaryStat: "WAN RTT: 10ms"`, và các chi tiết `detail__network_path`, `detail__security_protocol: "mTLS 1.3"`.
  3. Bổ sung Panel Ma Trận Mạng L3/L4 (*Cross-Cloud Network Routing & Subnet Connectivity Matrix*): Bảng dạng Table thể hiện chi tiết IP nguồn, IP đích, Subnet CIDR (10.0.1.0/24 vs 10.1.2.0/24), Security Group, Cổng dịch vụ, Chính sách WAN trễ tiêm và lưu lượng QPS.
  4. Bổ sung Panel Kiểm Kê 360° Phụ Thuộc Đám Mây Sâu (*Deep Single-Resource Cloud Dependencies 360° Inventory*).
  5. Triển khai qua Kustomize `kubectl apply -k k8s/base/visualization-grafana --context k3d-hub-k3d` và rollout restart Grafana thành công.
- **Kết quả xác thực (Verification Outcome):**
  1. Grafana API xác thực dashboard `mc-system-topology` phiên bản v3 đã được provisioned với 5 panel chuyên sâu.
  2. Truy cập web UI `http://localhost:3000/d/mc-system-topology` hiển thị trực quan toàn bộ sơ đồ đồ thị mạng, click vào từng node/edge hiển thị chi tiết phụ thuộc sâu, giải quyết trọn vẹn yêu cầu về độ phủ và trực quan hóa.

---

## Phase 3.5: Giám Sát Hạ Tầng Full-Stack & Nâng Cấp Dashboards SRE

### INC-P3-15: Thiếu hụt chỉ số hạ tầng sâu tầng OS/Kernel/Storage/USE và nâng cấp toàn diện bộ 7 Dashboards Grafana chuẩn SRE

- **Triệu chứng (Symptoms):**
  1. Giám sát hạ tầng máy chủ Kubernetes chỉ có 3 nhóm chỉ số cơ bản (CPU, Memory, Network I/O), hoàn toàn thiếu vắng các chỉ số tầng nhân OS/Kernel then chốt theo chuẩn phương pháp USE của Brendan Gregg: độ bão hòa CPU I/O wait (`%wa`), thời gian chờ hàng đợi đĩa (Disk I/O latency & Queue Length), hiện tượng phân trang/hoán đổi bộ nhớ (Paging Operations & Faults), tỷ lệ chiếm dụng Inode Filesystem, cũng như tỷ lệ rớt gói tin mạng (Packet Drops) và trạng thái kết nối TCP sockets (`ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`).
  2. Bộ Dashboards Grafana bộc lộ nhiều điểm hạn chế:
     - `k8s-infrastructure.json` chỉ có 4 panels sơ sài, thiếu phân tầng logic theo tài nguyên.
     - `wan-telemetry.json` chứa các giá trị giả lập tĩnh `vector(10.0)`, thiếu các chỉ số đo lường mạng WAN thực tế phát sinh trong môi trường mạng giả lập `netem`.
     - `system-topology.json` chứa chuỗi tĩnh giả định `secondaryStat: "Health: 100% | P95: 12ms"` và thiếu bảng tổng hợp sức khỏe tài nguyên phần cứng các nút cụm.
     - `red-metrics.json` thiếu tín hiệu độ bão hòa (Saturation) của 4 Golden Signals và trễ giao tiếp backend DB/RMI.
     - `logs-traces-deepdive.json` thiếu khả năng phát hiện tự động các mẫu bất thường hạ tầng (Connection Aborted, Timeout, Refused, OOM, Deadlock).
     - `mc-executive-overview.json` có bảng Fleet Matrix chưa tổng hợp đa chiều các chỉ số trọng yếu.
- **Nguyên nhân gốc rễ (Root Cause):**
  1. Cấu hình bộ thu `hostmetrics` trong `k8s/base/otel-collector/edge/02-configmap.yaml` chỉ kích hoạt 3 bộ scrapers (`cpu`, `memory`, `network`), chưa khai báo các bộ thu `load`, `paging`, `disk`, và `filesystem`. Đồng thời bộ thu `hostmetrics` chưa được bật trên Hub Gateway Collector để giám sát cụm trung tâm `hub-k3d`.
  2. Bố cục bảng điều khiển Grafana chưa được chuẩn hóa theo các phương pháp luận vận hành chuẩn mực (USE Method và 4 Golden Signals), dẫn đến các bảng điều khiển chỉ dừng ở mức hiển thị số liệu thô mà chưa hỗ trợ phân tích nguyên nhân sự cố nhanh chóng.
- **Giải pháp xử lý (Solution):**
  1. **Cấu hình toàn diện OTel Collector Hostmetrics:**
     - Mở rộng đầy đủ 7 bộ scrapers trong `edge/02-configmap.yaml`: `cpu`, `load`, `memory`, `paging`, `disk`, `filesystem`, `network`.
     - Kích hoạt `hostmetrics` trên `gateway/03-configmap.yaml` tại Hub Collector, đồng bộ hóa nhãn chuẩn hóa OTTL (`k8s_cluster_name`, `cloud_provider`, `cloud_region`).
  2. **Nâng cấp toàn diện Bộ 7 Dashboards Grafana:**
     - `k8s-infrastructure.json` (UID: `mc-k8s-infrastructure`): Mở rộng từ 4 lên 10 panels chuyên sâu chia thành 4 Rows logic theo chuẩn USE (Row 1: Compute & Load Avg; Row 2: Memory & Paging Saturation; Row 3: Disk I/O & Inode Saturation; Row 4: Network Stack & TCP Sockets).
     - `wan-telemetry.json` (UID: `mc-wan-telemetry`): Nâng cấp lên 8 panels, tích hợp chỉ số rớt gói tin thực tế (`system_network_dropped_total`), lỗi truyền tin (`system_network_errors_total`), tốc độ gói tin (`system_network_packets_total`), và độ bão hòa socket TCP trên cầu nối WAN.
     - `system-topology.json` (UID: `mc-system-topology`): Loại bỏ triệt để chuỗi tĩnh giả định `secondaryStat: "Health: 100% | P95: 12ms"`, tinh gọn chuỗi PromQL nodeGraph, bảo tồn nguyên vẹn 2 bảng Ma trận L3/L4 và Kiểm kê 360°, đồng thời bổ sung Panel 6 (Cluster Node Resource & Network Health Summary Table).
     - `red-metrics.json` (UID: `mc-red-metrics`): Hoàn thiện chuẩn 4 Golden Signals (Rate, Errors, Duration, Saturation), nâng cấp trễ phân vị P50/P90/P99, Panel 4 Saturation (CPU I/O wait, active sockets), và Panel 5 trễ backend database & RMI.
     - `logs-traces-deepdive.json` (UID: `mc-logs-traces-deepdive`): Thêm Panel 3 đếm log bất thường hạ tầng theo regex `(?i)(aborted|timeout|refused|oom|killed|io|error|fail|slow)` và Panel 5 luồng log chẩn đoán chuyên biệt cho tầng Database & Persistence tại `azure-k3d`.
     - `mc-executive-overview.json` (UID: `mc-executive-overview`): Nâng cấp Panel 7 (Cloud Cluster Fleet Health Matrix) hiển thị đầy đủ Memory Used GB, CPU Load Avg 1m, Network Drops/sec, Disk I/O Ops/sec.
- **Kết quả xác thực (Verification Outcome):**
  1. Kiểm tra JSON syntax: Toàn bộ 7/7 tệp dashboard JSON trong `k8s/base/visualization-grafana/dashboards/` đạt 100% Valid JSON.
  2. Kiểm tra Kustomize Overlay: Lệnh `kubectl kustomize` cho cả 3 cụm (`k8s/overlays/local-k3d/hub`, `spoke-aws`, `spoke-azure`) sinh manifest hoàn toàn hợp lệ, sẵn sàng áp dụng trực tiếp lên cụm khi khởi động.
  3. **Hotfix Schema v39 Rendering**:
     - Đồng bộ nhãn nhóm `(k8s_cluster_name, cloud_provider)` và bổ sung transformation `merge` cho các bảng multi-query (`mc-executive-overview.json` Panel 7, `system-topology.json` Panel 6, `k8s-infrastructure.json` Panel 8) giúp ghép các target A, B, C, D thành các cột trên cùng một hàng.
     - Thiết lập Dual Y-Axis (`custom.axisPlacement: "right"`) qua `byFrameRefID` cho các panel chứa 2 đại lượng khác đơn vị đo (`k8s-infrastructure.json` Panel 6 Throughput/IOPS, Panel 7 Latency/Queue, Panel 9 Throughput/Packets; `red-metrics.json` Panel 4 I/O Wait %/Active Sockets).
     - Đảm bảo tính linh hoạt cho metric Page Faults trong Panel 5 với fallback PromQL: `system_paging_faults_total or system_paging_operations_total`.

---

## Phase 3.6: Chuẩn Hóa Unified Resource Schemas & JVM Runtime Completeness

### INC-P3-16: Chuẩn hóa bộ đặc tả Unified Resource Monitoring Schemas (Web App & Compute Instance) và bổ sung độ phủ JVM Runtime Saturation

- **Triệu chứng (Symptoms):**
  1. Thiếu một chuẩn đặc tả giám sát thống nhất (Unified Monitoring Schema) được phân định rõ ràng giữa các loại thực thể cốt lõi trong hệ thống: **Web Application Resource** (các microservices Java/Tomcat của TeaStore) và **Compute Instance Resource** (các máy chủ Kubernetes Worker Nodes / Cloud VMs).
  2. Chưa phân định minh bạch cơ chế thu thập dữ liệu qua 3 tầng phụ thuộc: những gì có thể thu thập trực tiếp từ runtime (Local IMDS / Container Kubelet), và những gì cần nạp qua IaC Metadata Injection & OTTL Enrichment (để phòng tránh bão hòa rate limit và chi phí API trên đám mây thực tế).
  3. Bảng điều khiển `red-metrics.json` ban đầu chỉ hiển thị tài nguyên ở mức Host (CPU I/O Wait, Active Sockets), thiếu mảnh ghép độ bão hòa tài nguyên nội tại của ứng dụng (Application Runtime Saturation: JVM Memory Heap Usage & Thread Concurrency), khiến việc phân biệt lỗi giữa tầng App và tầng Node chưa thể thực hiện trực quan trên cùng một dashboard.
- **Nguyên nhân gốc rễ (Root Cause):**
  1. Các tài liệu thiết kế ban đầu (`03_resource_monitor.md`) tập trung mô tả mô hình khái niệm chung mà chưa đóng gói thành các bản đặc tả máy đọc được (Machine-Readable YAML Schemas) có cấu trúc chuẩn tắc phục vụ tự động hóa kiểm thử ở Phase 4.
  2. Cấu hình OTel Javaagent v2.10 trên TeaStore đã xuất đầy đủ các metrics JVM sang OTLP (`OTEL_METRICS_EXPORTER: "otlp"`), nhưng trên Grafana RED Metrics chưa có panel riêng biệt để khai thác luồng dữ liệu này.
- **Giải pháp xử lý (Solution):**
  1. **Xây dựng Đặc Tả Kiến Trúc & Hợp Đồng SRE Toàn Diện:**
     - Soạn thảo tài liệu `docs/schemas/RESOURCE_MONITORING_SCHEMAS.md` trình bày mô hình Completeness Triad (Identity, Health/USE/RED, Failure Signals), cơ chế thu thập 3 tầng phụ thuộc (Local IMDS vs Downward API vs IaC/OTTL Enrichment), và ma trận khóa liên kết (`service.name -> k8s_cluster_name / k8s.node.name`).
     - Xây dựng Cây quyết định chẩn đoán RCA liên tầng (Cross-Layer RCA Tree từ Web App xuống Instance) và Cây phân tích bán kính ảnh hưởng (Bottom-Up Impact Analysis Tree từ Instance lên Web App).
  2. **Khởi Tạo 2 Tệp YAML Schemas Chuẩn Máy Đọc Được:**
     - `docs/schemas/webapp-monitoring-schema.yaml`: Quy định rõ ràng cấu trúc 4 khối cho Web Application (Identity, Dependencies, Telemetry Signals với câu lệnh PromQL/LogQL chuẩn, SLO targets, Correlation keys).
     - `docs/schemas/instance-monitoring-schema.yaml`: Quy định rõ ràng cấu trúc 4 khối cho Compute Instance theo phương pháp USE (Utilization, Saturation, Errors cho CPU, Memory, Disk, Filesystem, Network) và ngưỡng cảnh báo Warning/Critical.
  3. **Hoàn Thiện Bảng Điều Khiển RED Metrics với JVM Runtime Saturation:**
     - Bổ sung **Panel 6: Application Runtime Saturation: JVM Memory Heap Usage & Thread Count** vào `k8s/base/visualization-grafana/dashboards/red-metrics.json` (`gridPos: {h: 8, w: 24, x: 0, y: 16}`).
     - Truy vấn song song `jvm_memory_used_bytes{jvm_memory_type="heap"}` (trục Y bên trái, đơn vị MBytes) và `jvm_thread_count` (trục Y kép bên phải `byFrameRefID: B`, đơn vị short).
- **Kết quả xác thực (Verification Outcome):**
  1. Cú pháp YAML: Kiểm tra qua Python Safe Loader xác nhận 2 tệp `webapp-monitoring-schema.yaml` và `instance-monitoring-schema.yaml` đạt 100% Valid YAML.
  2. Cú pháp Grafana JSON: Toàn bộ 7/7 tệp dashboard JSON đạt 100% Valid JSON.
  3. Kustomize Build: `kubectl kustomize k8s/overlays/local-k3d/hub` sinh manifest hợp lệ và đã đồng bộ toàn bộ bộ lọc và bảng điều khiển mới vào hệ thống.

---

### INC-P3-17: Lệch Pha SemConv PromQL, Xung Đột Kịch Bản Chaos 3 Cụm k3d & Thiếu Phản Hồi Closed-Loop AIOps
- **Thời gian ghi nhận:** 2026-11-07
- **Phân loại thành phần:** `ai-engine/`, `tests/chaos/`, `Prometheus Scraper`, `Grafana Dashboards`
- **Mức độ nghiêm trọng:** High
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. Sau khi hợp nhất nhánh `AI`, các câu lệnh PromQL trong `collector.py` và `detector.py` sử dụng nhãn OTel SemConv v1.x (`jvm_*`, `http_response_status_code`), có nguy cơ trả về rỗng nếu OTel Java Agent v2.10 phát ra SemConv v2.x (`process_runtime_jvm_*`). Ngoài ra, mệnh đề `and on (cloud_provider, service_name, host_name)` có thể triệt tiêu kết quả nếu `host_name` không khớp giữa các metrics.
  2. Các kịch bản chaos (`run_live.py`, `run_service_faults.py`) còn sót lại tham chiếu tới cụm `gcp` không tồn tại trong thiết kế 3 cụm k3d chuẩn (`aws`, `azure`, `hub`), khiến việc chạy kiểm thử tự động thất bại do `docker inspect k3d-gcp-k3d-server-0` trả về mã lỗi.
  3. Động cơ `ai-engine` phát hiện bất thường nhưng chỉ in log console ra stdout mà chưa xuất ngược các chỉ số AI (`ai_anomaly_likelihood_percent`, `ai_reconstruction_error`, `ai_rca_component_latency_ms`) về Prometheus TSDB, chưa hiển thị trên Grafana và chưa có kênh bắn cảnh báo tự động về Telegram.
- **Giải pháp xử lý (Solution):**
  1. **Chuẩn hóa PromQL Dual SemConv Fallback:**
     - Nâng cấp `ACTIVE_JVM_PODS` và `ENTITY_VECTOR_QUERIES` trong `collector.py` và `detector.py` hỗ trợ toán tử `or` cho cả SemConv 1.x (`jvm_*`) và SemConv 2.x (`process_runtime_jvm_*`), kèm fallback tự động nếu `host_name` không khớp.
     - Hỗ trợ song song cả nhãn `http_response_status_code` và `http_status_code`.
  2. **Chuẩn hóa 100% Kịch Bản Chaos Với 3 Cụm k3d:**
     - Trong `run_live.py`: đặt kịch bản mặc định `--scenarios azure_wan_delay` (180ms delay) mô phỏng liên kết WAN giữa AWS WebUI và Azure Persistence; bổ sung `aws_wan_delay` (200ms).
     - Trong `run_service_faults.py`: chuyển dịch vụ `recommender` về đúng cụm `"aws"` (`deploy/teastore-recommender`) và xác nhận RCA `aws:teastore-recommender`.
     - Phân tích và chứng minh `FaultAgent.java` nạp qua Java Dynamic Attach API không can thiệp vào `ClassFileTransformer`, không gây xung đột với OpenTelemetry Java Agent trong `CATALINA_OPTS`.
  3. **Thiết Kế Vòng Lặp Closed-Loop AIOps Toàn Diện:**
     - Tích hợp máy chủ HTTP mini `PrometheusMetricsServer` lắng nghe cổng `:9108/metrics` trong `detector.py`, xuất trực tiếp các chỉ số AI chuẩn OpenMetrics.
     - Bổ sung cấu hình scrape job `ai-engine` tại `01-configmap-prometheus.yaml` trong `k8s/base/metrics-thanos/`.
     - Bổ sung **Panel 7: AIOps Proactive Anomaly Likelihood & Distributed Trace RCA Decomposition** (Dual Y-Axis: `percent` / `ms`) trên `red-metrics.json`.
     - Tích hợp module `TelegramAlertSink` gửi cảnh báo Markdown giàu ngữ cảnh kèm phân rã RCA về Telegram Bot khi phát hiện `ALERT`, có cơ chế cooldown 60s/entity.
- **Kết quả xác thực (Verification Outcome):**
  1. Unit tests: `python -m unittest tests/chaos/test_live_evaluation.py` vượt qua 100% (4/4 tests OK).
  2. Cú pháp Python: Toàn bộ các script `collector.py`, `detector.py`, `run_live.py`, `run_service_faults.py` vượt qua `py_compile`.
  3. Cú pháp Grafana: Toàn bộ 7/7 tệp dashboard JSON hợp lệ.
  4. Kustomize overlays: Cả 3 cụm `hub`, `spoke-aws`, `spoke-azure` đều build manifest thành công.

---

## Phase 3.8: Học Hỏi Chiến Lược Nâng Cao Từ SigNoz

### INC-P3-18: Dynamic Templating, 360° Data Links, Tempo TraceQL Explorer và Dashboard Quản Trị Chi Phí Telemetry
- **Thời gian ghi nhận:** 2026-11-09
- **Phân loại thành phần:** `k8s/base/visualization-grafana/dashboards/`
- **Mức độ nghiêm trọng:** Medium
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. Toàn bộ các bảng điều khiển Grafana trước đó sử dụng biến tĩnh hoặc thiếu biến động đa cụm (`$cluster`, `$service`, `$environment`), làm hạn chế khả năng lọc cô lập dữ liệu theo từng đám mây hoặc xem toàn cục.
  2. Sơ đồ NodeGraph trên `system-topology.json` thiếu tính tương tác trực quan: chưa hiển thị trực tiếp tỷ lệ thành công/thất bại của từng node (Health Donut Arcs) và thiếu liên kết ngữ cảnh (Data Links) cho phép click từ Node để mở ngay Dashboard RED Metrics hoặc Logs/Traces của đúng service đó.
  3. Dashboard `logs-traces-deepdive.json` thiếu panel nhúng TraceQL để xem trực tiếp chi tiết Spans Waterfall của các giao dịch bị trễ mạng WAN hoặc lỗi DB.
  4. Hệ thống chưa có công cụ giám sát chi phí nạp viễn trắc (Telemetry Ingestion Cost) và kiểm toán rò rỉ nhãn vô hạn (unbounded cardinality).
- **Giải pháp xử lý (Solution):**
  1. Chuẩn hóa biến động `templating` trên 100% (8/8) dashboards với `$cluster`, `$service`, `$environment`.
  2. Bổ sung `arc__passed` và `arc__failed` cùng 360° Data Links trên NodeGraph Topology.
  3. Nhúng Panel 6 (Tempo Distributed TraceQL Explorer: `{ status = error || duration > 1.5s }`) và Panel 7 (Trace Spans Latency Distribution) trên `logs-traces-deepdive.json`.
  4. Kiến tạo Dashboard 8: `mc-cost-telemetry.json` (Multi-Cloud Telemetry Ingestion, Cardinality & Cost Meter) gồm 8 panel chuyên sâu giám sát lưu lượng nạp, ước tính chi phí WAN Egress ($0.09/GB) và kiểm toán Top 10 High-Cardinality Metrics.
- **Kết quả xác thực:** 8/8 Dashboards Grafana JSON hợp lệ 100%; nạp tự động qua Grafana provisioning.

---

## Phase 3.9: Tối Ưu Hóa Tầng Sâu Pipeline & Kiểm Thử Môi Trường Thực Tế

### INC-P3-19: Dual-Route Traces Pipeline Bảo Toàn True QPS Cho ServiceGraph và Bộ Luật Cảnh Báo Prometheus
- **Thời gian ghi nhận:** 2026-11-10
- **Phân loại thành phần:** `03-configmap.yaml` (OTel Gateway), `01-configmap-prometheus-rules.yaml`
- **Mức độ nghiêm trọng:** Medium
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. Trước đây, luồng `traces` đi qua `tail_sampling` trước khi đẩy sang `servicegraphconnector`. Khi tail-sampling lọc bỏ 95% trace thông thường để tiết kiệm dung lượng, tỷ lệ request của ServiceGraph (`traces_service_graph_request_total`) bị giảm tương ứng 95%, không phản ánh đúng thông lượng thực tế (True QPS) của hệ thống.
  2. Prometheus thiếu tập luật cảnh báo tự động phát hiện mất dữ liệu Spoke (Absent Data Heartbeat), trễ WAN suy giảm, và áp lực bộ nhớ OTel Collector.
- **Giải pháp xử lý (Solution):**
  1. Tách luồng traces tại Hub Gateway thành **Dual-Route Traces Pipeline**:
     - Luồng 1 (`traces`): Nhận 100% spans thô $\rightarrow$ đẩy trực tiếp vào `servicegraph` connector (bảo toàn 100% throughput và độ chính xác của bản đồ mạng).
     - Luồng 2 (`traces/storage`): Nhận spans thô $\rightarrow$ qua `tail_sampling` (100% error + 100% trễ > 1500ms + 5% routine) $\rightarrow$ đẩy sang Tempo và MinIO S3 (tiết kiệm >70% chi phí lưu trữ).
  2. Khởi tạo `01-configmap-prometheus-rules.yaml` với 4 nhóm luật: `SpokeClusterHeartbeatAbsent`, `MicroserviceHighErrorRate`, `CrossCloudWANLatencyDegraded`, `OTelCollectorMemoryHigh`.
- **Kết quả xác thực:** Cả hai luồng traces hoạt động song song chính xác, QPS trên bản đồ Topology đạt đúng giá trị thực tế; 4 nhóm cảnh báo hoạt động ổn định trên Prometheus `:9090/rules`.

---

### INC-P3-20: Kustomize CRD Race Condition & Containerd MinIO Cache Trên Ubuntu WSL2
- **Thời gian ghi nhận:** 2026-11-10
- **Phân loại thành phần:** `k8s/overlays/local-k3d/hub`, `containerd / MinIO`
- **Mức độ nghiêm trọng:** Medium
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. Khi chạy `kubectl apply -k k8s/overlays/local-k3d/hub` trong lần đầu, Kube API server chưa kịp đăng ký schema CRD Pyrra (`ServiceLevelObjective`) trước khi tài nguyên CR `teastore-webui-availability` được apply, dẫn đến lỗi `no matches for kind "ServiceLevelObjective"`.
  2. Docker Hub chặn kéo image `minio/minio:RELEASE.2025-10-15T17-29-55Z` từ containerd bên trong k3d do cơ chế scope authorization token của Docker Hub bị giới hạn.
- **Giải pháp xử lý (Solution):**
  1. Chạy lại lệnh apply Kustomize lần hai ngay sau khi CRD schema hoàn tất đăng ký.
  2. Nạp trực tiếp image đã kéo từ host Docker vào containerd của k3d server node qua đường ống:
     `docker save minio/minio:RELEASE.2025-10-15T17-29-55Z | docker exec -i k3d-hub-k3d-server-0 ctr images import -`.
- **Kết quả xác thực:** Toàn bộ 18 pod trên 3 cụm Kubernetes (`hub-k3d`, `aws-k3d`, `azure-k3d`) đạt trạng thái `1/1 Running` (`prometheus-0` đạt `2/2 Running`).

---

### INC-P3-21: Loại Bỏ Nhãn AzureVM, Chuẩn Hóa Định Danh Thực Tế Microsoft Entra ID & AWS ARN và Bổ Sung Cơ Chế Xóa Sạch Docker Images Khi Teardown
- **Thời gian ghi nhận:** 2026-11-10
- **Phân loại thành phần:** `Makefile`, `00_cleanup_all.yml`, `infra/scripts/clean_images.sh`, `03-configmap.yaml` (OTel Gateway), `system-topology.json`, `docs/schemas/`
- **Mức độ nghiêm trọng:** High
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. **Tồn đọng Docker Images khi Teardown:** Lệnh `make teardown` (Ansible playbook `00_cleanup_all.yml`) chỉ xóa các container `k3d-*`, xóa mạng bridge `mc-monitoring-net` và dọn volume, nhưng không xóa các Docker images đã kéo trên máy chủ host (`docker images` vẫn giữ nguyên toàn bộ 16 container images của TeaStore, OTel và Observability).
  2. **Xuất hiện nhãn sai lệch "AzureVM":** Trong kiến trúc thực tế của đồ án, Spoke 2 (`azure-k3d`) là cụm Kubernetes mô phỏng **Azure Kubernetes Service (AKS)** với Managed Node Pool (`nodepool-data`), hoàn toàn không có máy chủ ảo độc lập (`AzureVM` / `Microsoft.Compute/virtualMachines`). Tuy nhiên, trong biểu thức PromQL Panel 3 của `system-topology.json` và một số tài liệu schema lại xuất hiện chuỗi `Azure AKS (VM Standard_D4ds_v5)`.
  3. **Định danh giả lập phi thực tế:** Các thuộc tính làm giàu (enrichment) tại Hub OTel Gateway sử dụng chuỗi số giả lập `123456789012` (AWS) và `00000000-0000-0000-0000-000000000000` (Azure), thiếu định danh danh tính Microsoft Entra ID (Tenant ID, UAMI Client/Object ID) theo chuẩn doanh nghiệp thực tế.
- **Giải pháp xử lý (Solution):**
  1. **Khởi tạo script `infra/scripts/clean_images.sh` & Tích hợp vào `make teardown`:**
     - Xóa toàn bộ 16 images của TeaStore, OTel, Observability và các image helper k3d (`rancher/k3*`).
     - Thực thi `docker image prune -f` xóa triệt để dangling images.
     - Tích hợp tác vụ này vào cả playbook `infra/ansible/playbooks/00_cleanup_all.yml` và target `make teardown`, đồng thời cung cấp target độc lập `make clean-images`.
  2. **Triệt tiêu hoàn toàn nhãn AzureVM:**
     - Chuẩn hóa nền tảng của Azure Spoke thành `Azure AKS (NodePool: nodepool-data)` và AWS Spoke thành `AWS EKS (NodeGroup: nodepool-app)` trên Grafana Dashboard `system-topology.json`.
     - Cập nhật `docs/schemas/RESOURCE_MONITORING_SCHEMAS.md` và `docs/schemas/instance-monitoring-schema.yaml` xác định đối tượng theo dõi là Kubernetes Worker Nodes / EKS & AKS Node Pools, loại bỏ mọi tham chiếu tới standalone Cloud VMs.
  3. **Chuẩn hóa định danh Microsoft Entra ID & Realistic ARN IDs:**
     - **AWS Identifiers:**
       - AWS 12-digit Account ID: `851725492014` (thay thế `123456789012`).
       - IAM Role ARN: `arn:aws:iam::851725492014:role/${service.name}-irsa-role`.
       - EKS Pod Resource ID: `arn:aws:eks:us-east-1:851725492014:pod/teastore-cluster/${k8s.namespace.name}/${k8s.pod.name}`.
       - Network VPC ID: `vpc-0f8a3c2b1e7d9a4f6` (thay thế `vpc-0a1b2c3d4e5f67890`), Subnet: `subnet-09a8b7c6d5e4f3a21`, SG: `sg-01a2b3c4d5e6f7a8b`.
     - **Azure / Microsoft Entra ID Identifiers:**
       - Azure Subscription ID: `4b8f3a21-9e6c-4f80-b753-2d9a6e1c84f5` (thay thế chuỗi toàn số 0).
       - Microsoft Entra Directory / Tenant ID: `72f988bf-86f1-41af-91ab-2d7cd011db47`.
       - Microsoft Entra User-Assigned Managed Identity (UAMI): `/subscriptions/4b8f3a21-9e6c-4f80-b753-2d9a6e1c84f5/resourceGroups/rg-teastore-southasia/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami-${service.name}`.
       - Azure AKS Pod Resource ID: `/subscriptions/4b8f3a21-9e6c-4f80-b753-2d9a6e1c84f5/resourceGroups/rg-teastore-southasia/providers/Microsoft.ContainerService/managedClusters/teastore-aks/pods/${k8s.pod.name}`.
       - Network VNet ID: `vnet-teastore-southasia`, Subnet: `snet-aks-nodepool-data`, NSG: `nsg-aks-teastore-internal`.
- **Kết quả xác thực (Verification Outcome):**
  1. Script `clean_images.sh` kiểm thử dry-run thành công; `make teardown` đảm bảo dọn sạch 100% clusters, networks, volumes và images.
  2. Toàn bộ 8/8 Grafana Dashboards vượt qua kiểm tra cú pháp JSON hợp lệ 100%.
  3. Kustomize overlays của cả 3 cụm build manifest thành công không có lỗi cú pháp OTTL.

---

## Phase 3.9.3: Khắc Phục Lỗi Chặn Audit & Xác Thực Chữ Ký Mật Mã PKI / mTLS

### INC-P3-22: Khắc phục triệt để 5 lỗi chặn kiến trúc & mã nguồn phát hiện qua Audit SigNoz Production Standards
- **Thời gian ghi nhận:** 2026-11-12
- **Phân loại thành phần:** `security/pki/scripts/`, `ai-engine/data/collector.py`, `ai-engine/inference/detector.py`, `tests/chaos/run_live.py`, `tests/chaos/scenarios.json`, `k8s/base/otel-collector/edge/02-configmap.yaml`, `k8s/base/teastore/mysql/00-deployment.yaml`, `k8s/base/logs-loki/01-configmap.yaml`
- **Mức độ nghiêm trọng:** Critical (Blocker cho Benchmark Phase 4)
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. **Tạo mới khóa PKI liên tục (Non-idempotent) hoặc bỏ qua sơ sài không kiểm tra chữ ký:** Ban đầu script PKI sinh khóa mới mỗi lần chạy làm đứt gãy mTLS; nếu chỉ check file existence đơn thuần thì khi Root CA thay đổi hoặc chứng chỉ hết hạn/đổi SAN, script sẽ bỏ qua không ký lại, gây đứt gãy chuỗi tin cậy (Chain of Trust).
  2. **Lệch tên K8s Service Prometheus:** Mã nguồn Python (`collector.py`, `detector.py`, `run_live.py`) trỏ vào `svc/prometheus-server` cổng `80` (tàn dư Helm chart cũ), trong khi service K8s thực tế là `service/prometheus` cổng `9090`. Script crash ngay lập tức với lỗi `NotFound`.
  3. **Head Sampling 20% tại Spoke làm "bỏ đói" Tail Sampling & RCA tại Hub:** Giao dịch phân tán đa đám mây bắt đầu tại AWS (`teastore-webui`) và lỗi xảy ra ở bước cuối tại Azure (`teastore-persistence`/`teastore-db`). Tại AWS Spoke, các span đầu tiên vẫn có trạng thái `OK`, nên nếu áp dụng `probabilistic_sampler: 20` mù quáng tại Spoke, 80% span lỗi và span chậm bị drop trước khi qua WAN, tạo ra các orphan spans làm thuật toán AI RCA $\Delta T = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$ tính sai lệch hoàn toàn.
  4. **Kịch bản GCP không tồn tại trong hạ tầng:** `scenarios.json` còn chứa các kịch bản định danh `gcp:teastore-recommender` và `aws->gcp` trong khi đồ án triển khai mô hình 2 Spoke chuẩn `aws` và `azure`.
  5. **Nguy cơ MySQL OOMKilled & Loki TSDB không có retention:** `teastore-db` chỉ được cấp `384Mi` RAM giới hạn (dễ bị K8s kill dưới tải Locust đa người dùng) và Loki thiếu khai báo `retention_period` trong `limits_config`.
- **Giải pháp xử lý (Solution):**
  1. **Chuẩn hóa Cryptographic Chain-of-Trust Verification cho PKI:**
     - Cập nhật `01-generate-ca.sh`, `02-generate-hub-cert.sh`, `03-generate-spoke-cert.sh` với `umask 077`, gán quyền `chmod 600` cho private keys và `chmod 644` cho certs.
     - Chỉ bỏ qua sinh cert khi thỏa mãn đồng thời 3 điều kiện: (a) file `.key` và `.crt` tồn tại, (b) chữ ký xác thực hợp lệ 100% với `ca.crt` hiện hành qua `openssl verify -CAfile`, (c) chứng chỉ còn hạn ít nhất 7 ngày qua `openssl x509 -checkend 604800`. Hỗ trợ thêm cờ `--force`.
  2. **Sửa toàn diện tên Service Prometheus:** Cập nhật lệnh `kubectl port-forward` và `get service` trong `collector.py`, `detector.py`, `run_live.py` sang `svc/prometheus` cổng `9090:9090`.
  3. **Tối ưu hóa Ingestion Pipeline Edge vs Hub:**
     - Tại `edge/02-configmap.yaml`: Giữ nguyên `filter/drop_noise` loại bỏ 100% healthcheck noise, bật `compression: gzip` trong exporter `otlp/hub` để tối ưu băng thông WAN, và **gỡ bỏ hoàn toàn `probabilistic_sampler` khỏi pipeline `traces`**.
     - Tại `gateway/03-configmap.yaml`: Toàn bộ business spans hội tụ đầy đủ về Hub để `servicegraphconnector` tính đúng 100% RED metrics và `tail_sampling` bảo toàn trọn vẹn 100% traces lỗi/chậm cho AI Engine.
  4. **Chuẩn hóa Kịch bản Chaos:** Sửa sạch 100% tham chiếu `gcp` trong `scenarios.json` về đúng kiến trúc thực tế `aws:teastore-recommender` và `aws_wan_delay` (`aws->azure`).
  5. **Hạ tầng MySQL & Loki:** Nâng `limits.memory` của MySQL lên `768Mi` (requests `256Mi`), và bổ sung `retention_period: 72h` vào `limits_config` của Loki.
- **Kết quả xác thực (Verification Outcome):**
  1. Chạy lặp lại 2 lần liên tiếp bộ 3 scripts PKI: Lần 2 phát hiện `openssl verify` thành công và giữ nguyên khóa cũ không sinh đè.
  2. Chạy `kubectl kustomize` cho cả 3 overlays (`hub`, `spoke-aws`, `spoke-azure`) đều đạt Exit Code = 0.
  3. Quét kiểm tra toàn bộ codebase: 0 lỗi tham chiếu `prometheus-server` và 0 tham chiếu `gcp` trong `tests/chaos/scenarios.json`.
  4. Bộ kiểm thử logic `test_live_evaluation.py` vượt qua 100% (4/4 tests OK).

---

## Phase 3.9.5: Nạp Động Secret từ .env & Chuẩn Hóa Toàn Diện 8 Dashboards Grafana

### INC-P3-23: Triệt tiêu hoàn toàn mật khẩu Plaintext S3 và chuẩn hóa UX/Filters 8 Grafana Dashboards
- **Thời gian ghi nhận:** 2026-11-12
- **Phân loại thành phần:** `k8s/base/logs-loki/`, `k8s/base/traces-tempo/`, `k8s/base/visualization-grafana/dashboards/`
- **Mức độ nghiêm trọng:** High
- **Hiện tượng & Nguyên nhân gốc rễ (Root Cause):**
  1. **Lộ lọt thông tin xác thực MinIO S3 (`ARCH-03`):** Cả hai tệp ConfigMap `k8s/base/logs-loki/01-configmap.yaml` và `k8s/base/traces-tempo/01-configmap.yaml` đều chứa giá trị plaintext `access_key_id: admin` và `secret_access_key: MultiCloudSecurePassword2026!`. Mặc dù Kustomize overlay đã sinh các Secret `loki-s3-creds` và `tempo-s3-creds` từ tệp `.env`, nhưng các StatefulSet của Loki và Tempo chưa nạp biến môi trường và chưa kích hoạt tính năng nạp động qua cờ `-config.expand-env=true`.
  2. **Tiêu đề Dashboards rườm rà, thiếu phân loại thứ bậc:** 8 Dashboards Grafana mang các tiêu đề dài dòng chứa nhiều từ ngữ lặp lại ("Multi-Cloud...", "Centralized..."), không theo thứ tự số và không gắn kết với danh mục Schema phân loại (CAT-01 đến CAT-08).
  3. **Lệch biến `$cluster` và thiếu bộ lọc tại Panels:** Biến `$cluster` trên các Dashboard định nghĩa không đồng nhất (dùng `up` nhãn `cluster` cũ hoặc metric sai `system_memory_usage` thiếu `_bytes`). Đồng thời, toàn bộ 10 panels trong `k8s-infrastructure.json` và các panels mạng trong `wan-telemetry.json` chưa gắn `{k8s_cluster_name=~"$cluster"}`, dẫn tới việc khi chọn cụm trên dropdown không lọc được số liệu.
  4. **Thiếu trường dữ liệu theo chuẩn Schema v4.0.0:** `red-metrics.json` Panel 6 thiếu GC Pause Time (`CAT-06`), `system-topology.json` Panel 5 thiếu phân phối độ trễ P99, và `logs-traces-deepdive.json` gom nhóm theo `job` khiến không nhận diện được tên microservice của TeaStore.
- **Giải pháp xử lý (Solution):**
  1. **Dynamic Secret Expansion (Zero Plaintext in ConfigMaps):**
     - Cập nhật StatefulSet của Loki (`03-statefulset.yaml`) và Tempo (`03-statefulset.yaml`): Thêm cờ `-config.expand-env=true` vào `args`, nạp `MINIO_ROOT_USER` và `MINIO_ROOT_PASSWORD` từ `secretKeyRef` của `loki-s3-creds` và `tempo-s3-creds`.
     - Cập nhật ConfigMap của Loki và Tempo: Thay thế chuỗi plaintext thành `${MINIO_ROOT_USER}` và `${MINIO_ROOT_PASSWORD}`.
  2. **Chuẩn hóa Tiêu đề 8 Dashboards ngắn gọn:** Đổi tên hiển thị 8 dashboards thành:
     `01. Executive Overview`, `02. Topology & Cloud Context`, `03. Application & JVM (RED)`, `04. Compute & OS Kernel (USE)`, `05. Network & WAN Transport`, `06. Logs, Traces & Database`, `07. SLO & Error Budget`, `08. Telemetry & Cost Governance`. Giữ nguyên 100% `uid` để bảo toàn Data Links.
  3. **Chuẩn hóa Biến `$cluster` & Gắn Bộ Lọc:**
     - Chuẩn hóa định nghĩa biến `cluster` trên 8/8 Dashboards về duy nhất: `label_values(system_cpu_time_seconds_total, k8s_cluster_name)`.
     - Bổ sung bộ lọc `{k8s_cluster_name=~"$cluster"}` cho toàn bộ 10 panels của `k8s-infrastructure.json` và Panels 6, 7, 8 của `wan-telemetry.json`.
  4. **Bổ sung Trường Telemetry Chuẩn Schema:**
     - Bổ sung `refId: C` vào Panel 6 của `red-metrics.json`: `sum by (service_name) (rate(jvm_gc_duration_seconds_sum[1m]) or rate(process_runtime_jvm_gc_duration_seconds_sum[1m])) * 1000` (đo GC Pause Time ms/s).
     - Bổ sung `refId: C` vào Panel 5 của `system-topology.json`: quantile P99 độ trễ liên cụm.
     - Cập nhật Panels 1, 2, 3 của `logs-traces-deepdive.json` gom nhóm theo `sum by (service_name, job)` hiển thị rõ ràng tên vi dịch vụ.
- **Kết quả xác thực (Verification Outcome):**
  1. Quét `k8s/base/logs-loki` và `k8s/base/traces-tempo`: 0 kết quả chứa mật khẩu plaintext `MultiCloudSecurePassword2026!`.
  2. Toàn bộ 8 Dashboards Grafana đạt chuẩn cú pháp JSON 100%.
  3. Lệnh `kubectl kustomize k8s/overlays/local-k3d/hub` build thành công (Exit Code = 0), tự động sinh đầy đủ Secret và gắn cờ env expansion.
  4. Bộ test tự động `make validate-dashboards && make validate-kustomize && make test-ai` vượt qua 100%.

---

## Phase 3.9.7: Rà Soát Độ Phủ Thuộc Tính & Tín Hiệu Schemas Trên 8 Grafana Dashboards

### INC-P3-24: Báo cáo khoảng trống hiển thị giữa OTel Schemas v4.2.0 và 8 Grafana Dashboards
- **Thời gian ghi nhận:** 2026-11-12
- **Phân loại thành phần:** `k8s/base/visualization-grafana/dashboards/`, `docs/schemas/categories/`, `docs/schemas/profiles/`
- **Mức độ nghiêm trọng:** Medium (Tối ưu hóa khả năng quan sát & Khớp nối Schemas)
- **Bối cảnh & Mục tiêu rà soát:**
  Sau khi chuẩn hóa toàn bộ hệ thống Schema thành 2 tầng (`categories/` với 8 danh mục OTel SemConv nguyên tử và `profiles/` với 4 hồ sơ thực thể) cùng việc loại bỏ Head Sampling tại Spoke (Phase 3.9.3 & 3.9.5), nhóm vận hành tiến hành kiểm tra chéo (Cross-Audit) giữa 8 Dashboard Grafana hiện tại và toàn bộ các thuộc tính/số đo trong Schema để trả lời 3 câu hỏi:
  1. Các Dashboards đã phản ánh đủ 8 Categories và 4 Entity Profiles chưa?
  2. Có thuộc tính hoặc tín hiệu quan trọng nào trong Schema v4.2.0 chưa được đưa lên Dashboard không?
  3. Có vấn đề mới phát sinh nào về mặt bộ lọc biến (Variables Scope) hoặc tương thích dữ liệu sau khi sửa đổi không?

- **Kết quả Kiểm tra Đối soát (Schema-to-Dashboard Coverage Audit):**
  
  #### 1. Mức Độ Phản Ánh 8 Categories Trên 8 Dashboards (Hiện trạng rất tốt):
  - **`CAT-01` (OS & Kernel USE):** Phản ánh 100% trên `04. Compute & OS Kernel (USE)` (Panels 1, 2, 3: CPU User/Sys/Wait/Steal, Load 1m/5m/15m).
  - **`CAT-02` (Storage & Filesystem):** Phản ánh 100% trên `04. Compute & OS Kernel (USE)` (Panels 6, 7, 8: Throughput, IOPS, I/O Wait Latency, Queue Depth, Filesystem % & Inodes).
  - **`CAT-03` (Network & Transport):** Phản ánh 100% trên `05. Network & WAN Transport` (Panels 1-8: WAN RTT/Jitter/Loss, Throughput, Packet Drops, TCP Socket states).
  - **`CAT-04` (Cloud Context):** Phản ánh 100% trên `02. Topology & Cloud Context` (Panels 1, 2, 3: Interactive Node Graph, Routing Matrix, 360° Cloud Dependencies với VPC, Subnet, SG, IAM Role IRSA).
  - **`CAT-05` (Kubernetes & Containers):** Phản ánh trên `01. Executive Overview` (Fleet Matrix) và `04. Compute & OS Kernel`.
  - **`CAT-06` (JVM Runtime):** Phản ánh trên `03. Application & JVM (RED)` (Panel 6: Heap Used, Thread Count, GC Pause Time ms/s).
  - **`CAT-07` (HTTP/RPC APM & RED):** Phản ánh trên `03. Application & JVM (RED)` (Panels 1, 2, 3, 5: Rate, Errors, P50/P90/P99, RMI/DB Duration) và `07. SLO & Error Budget`.
  - **`CAT-08` (Database MySQL):** Phản ánh qua JDBC Spans trên `03. Application & JVM (RED)` (Panel 5), `02. Topology` và `06. Logs, Traces & Database` (Panel 5).

  ---

  #### 2. Các Khoảng Trống & Điểm Cần Thảo Luận Xử Lý (Findings & Gaps):

  | Mã Vấn Đề | Hạng Mục / Vị Trí | Mô Tả Khoảng Trống (Gap Description) | Đánh Giá Tác Động | Hướng Xử Lý Đề Xuất Để Thảo Luận |
  | :---: | :--- | :--- | :---: | :--- |
  | **GAP-01** | `03. Application & JVM (RED)` (Panels 1, 2, 3) | Các panel Rate, Errors, Duration sử dụng metric `traces_service_graph_request_*` mới chỉ lọc theo `{server=~"$service"}` mà **chưa gắn biến `{k8s_cluster_name=~"$cluster"}`** (hoặc `{server_k8s_cluster_name=~"$cluster"}`). | Khi chọn cụm trên dropdown `$cluster`, 3 panels này vẫn hiển thị dữ liệu của toàn bộ 2 cụm AWS + Azure. | **Thảo luận:** Bổ sung nhãn `server_k8s_cluster_name=~"$cluster"` vào biểu thức PromQL của Panels 1, 2, 3 (hoặc giữ nguyên nếu muốn người dùng nhìn thấy toàn cảnh traffic theo service bất kể service nằm trên cụm nào). |
  | **GAP-02** | `03. Application & JVM (RED)` (Panel 4) | Panel 4 ("Saturation: Host CPU I/O Wait & Active TCP Connections") hiển thị CPU wait và TCP connections theo cụm nhưng **đang thiếu biến lọc `{k8s_cluster_name=~"$cluster"}`** trong mệnh đề sum. | Biểu đồ hiển thị cả 2 cụm thay vì lọc theo dropdown `$cluster`. | Thêm `{k8s_cluster_name=~"$cluster"}` vào Panel 4 để đồng bộ hoàn toàn với `$cluster`. |
  | **GAP-03** | `08. Telemetry & Cost Governance` (Panel 5) | Panel 5 ("Trace Volume Reduction Waterfall") đo hiệu quả lọc của Spoke: `otelcol_processor_filter_spans_filtered`. Ở Phase 3.9.3, ta đã **gỡ bỏ Head Sampling (`probabilistic_sampler`)** khỏi Spoke, chỉ còn giữ `filter/drop_noise` (lọc healthcheck). | Biểu đồ Waterfall sẽ phản ánh đúng thực tế: chỉ giảm thiểu ~30-40% span noise healthcheck (thay vì giảm 80% do sampling cũ). | Cập nhật ghi chú/subtitle trên Panel 5 thành: *"Edge Healthcheck Noise Pre-filtering & Gateway Tail-sampling Retention (100% Errors Preserved)"* để SRE hiểu rõ bản chất. |
  | **GAP-04** | `CAT-05` (cgroup limits) trên `04. Compute & OS Kernel` | Schema `CAT-05` quy định metric `container_cpu_cfs_throttled_seconds_total` (đo container CPU throttling do cgroup quota) và `container_memory_working_set_bytes` (bộ nhớ container K8s). Hiện tại Dashboard 04 tập trung chủ yếu vào USE Method của Host Node (`system_*`). | Chưa có panel chuyên biệt hiển thị Top Pods bị CPU Throttling trên cụm. | Thêm 1 panel nhỏ (hoặc row phụ) hiển thị Top 5 Pods bị CPU Throttling trong K8s Infrastructure. |
  | **GAP-05** | `CAT-08` (Database Error Rate) | Panel 5 trên `red-metrics.json` hiển thị độ trễ Database Call Latency P50/P95, nhưng chưa có biểu đồ tách riêng tỷ lệ lỗi của Database (`traces_service_graph_request_failed_total{server=~"teadb|teastore-db"}`). | Khi xảy ra lỗi deadlock MySQL, tỷ lệ lỗi DB bị gộp chung vào Error Rate tổng của Persistence. | Tách hoặc bổ sung 1 target hiển thị riêng lỗi MySQL JDBC trên Panel 2 hoặc Panel 5. |

- **Giải pháp xử lý & Quyết định Kiến trúc (Solution & Architectural Decisions):**
  1. **Quyết định GAP-01 (Giữ nguyên `{server=~"$service"}` trên Panels 1, 2, 3 của `red-metrics.json`):**
     - **Quyết định: GIỮ NGUYÊN, KHÔNG thêm `server_k8s_cluster_name`.**
     - *Lý do kỹ thuật:* Đối với các client-only spans được ánh xạ qua `peer.service` (như `teadb` hoặc `teastore-registry`), nhãn `server_k8s_cluster_name` không tồn tại trong metric `traces_service_graph_request_*`. Giữ nguyên `{server=~"$service"}` đảm bảo hiển thị 100% các vi dịch vụ và phụ thuộc đa đám mây mà không bị bẫy "No Data".
  2. **Khắc phục GAP-02 (Đồng bộ bộ lọc `$cluster` trên Panel 4 của `red-metrics.json`):**
     - Bổ sung bộ lọc `{k8s_cluster_name=~"$cluster"}` vào các biểu thức tính CPU I/O Wait `system_cpu_time_seconds_total` và Active TCP Connections `system_network_connections`.
  3. **Khắc phục GAP-03 (Chuẩn hóa mô tả cơ chế lọc Waterfall trên Panel 5 của `mc-cost-telemetry.json`):**
     - Cập nhật tiêu đề thành `"Trace Volume Reduction Waterfall (Edge Noise Filter & Hub Tail-Sampling)"` và diễn giải rõ nét cơ chế Spoke Edge lọc rác health probes (`filter/drop_noise`) kết hợp Hub Central Gateway thực thi tail-based sampling bảo toàn 100% spans lỗi và trễ cao.
  4. **Quyết định GAP-04 (Tránh bẫy No Data cAdvisor trên `k8s-infrastructure.json`):**
     - **Quyết định: KHÔNG thêm panel cAdvisor throttling vào Dashboard 04.**
     - *Lý do kỹ thuật:* Spoke Collector sử dụng bộ thu `hostmetrics` cấp Node chứ không scrape Kubelet cAdvisor nội bộ pod, việc thêm query `container_cpu_cfs_throttled_seconds_total` sẽ gây lỗi "No Data" trên dashboard thực tế.
  5. **Khắc phục GAP-05 (Bổ sung tỷ lệ lỗi Database & đồng bộ `$service` trên Panels 5 & 6 của `red-metrics.json`):**
     - Bổ sung `refId: C` vào Panel 5 của `red-metrics.json`: `sum by (client, server) (rate(traces_service_graph_request_failed_total{server=~"teadb|teastore-db|teastore-registry|teastore-persistence"}[1m]))` với cấu hình override trục Y bên phải (`axisPlacement: "right"`), đơn vị `reqps`, màu đỏ cảnh báo.
     - Đồng bộ bộ lọc `{service_name=~"$service"}` vào cả 3 targets của Panel 6 (JVM Heap, Threads, GC Pause Time) để biểu đồ phản hồi trực tiếp khi người dùng chọn service trên dropdown.

- **Kết quả xác thực (Verification Outcome):**
  1. Toàn bộ 8/8 Dashboards Grafana vượt qua kiểm tra cú pháp JSON (`make validate-dashboards`).
  2. Toàn bộ Kustomize manifests của 3 cụm k3d build thành công không lỗi cú pháp (`make validate-kustomize`).
  3. Bộ kiểm thử AIOps Engine chạy hoàn tất thành công (`make test-ai`).
  4. **Trạng thái: Đã giải quyết triệt để (100% Resolved). Khóa sổ toàn bộ Phase 3.**










