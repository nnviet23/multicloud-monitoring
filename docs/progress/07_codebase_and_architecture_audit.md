# Báo Cáo Kiểm Toán Toàn Diện Mã Nguồn & Kiến Trúc Đối Chiếu Chuẩn SigNoz Production (Deep Codebase & Architecture Audit)

> **Mã tài liệu:** `docs/progress/07_codebase_and_architecture_audit.md`  
> **Chuyên đề:** Rà Soát Sâu Toàn Bộ Mã Nguồn, Cấu Hình K8s, Pipeline OTel và AI Engine Trước Thử Nghiệm Benchmark  
> **Vị trí thực hiện:** Principal Observability Architect, Senior Kubernetes/OpenTelemetry SRE & Systems Auditor  
> **Hệ quy chiếu chuẩn:** Kiến trúc Production của SigNoz (`docs/progress/05_SigNoz_strategy.md`), OpenTelemetry Best Practices và Kubernetes Reliability Guidelines  
> **Phạm vi kiểm toán (Strict Read-Only):** `k8s/`, `infra/`, `security/`, `ai-engine/`, `tests/`, `Makefile`  
> **Ngày hoàn thành:** 2026-11-12

---

## Tóm Tắt Điều Hành (Executive Summary)

Đợt kiểm toán kỹ thuật toàn diện này rà soát toàn bộ các thành phần trên nhánh `feat/integrate-infra-ai-anomaly` nhằm bảo đảm hệ thống sẵn sàng cho **Phase 4: Benchmark, Chaos Engineering Experiments & Closed-Loop AIOps Evaluation**.

Bằng việc lấy **Kiến trúc Vận hành Thực tế của SigNoz (SigNoz Production Standards)** làm hệ quy chiếu chuẩn mực, báo cáo này chỉ ra:
1. **03 Lỗi Chặn / Nghiêm Trọng (Critical / Blocker Bugs):**
   - Tên Service của Prometheus bị lệch giữa code Python (`svc/prometheus-server`) và K8s manifest (`svc/prometheus`), chắc chắn sẽ làm gãy các kịch bản chaos tự động và port-forward của `ai-engine`.
   - Mâu thuẫn chết người giữa **Head Sampling mù quáng (20% tại Spoke)** và **Tail Sampling tại Hub**, khiến 80% span lỗi và trễ cao bị tiêu diệt ngay tại biên trước khi kịp tới Hub, làm đói dữ liệu của AI RCA và sai lệch Service Graph.
   - Cơ sở dữ liệu `teastore-db` MySQL 8.0 chạy dưới dạng `Deployment` không có PVC lưu trữ bền vững (Ephemeral data) và bị giới hạn RAM ở mức nguy hiểm 384Mi.
2. **04 Đánh Đổi Kiến Trúc (Architectural Trade-offs - k3d Lab vs. Production):**
   - Spoke Collector đang chạy dạng `Deployment 1-replica` thay vì mô hình 2 tầng chuẩn SigNoz (**DaemonSet Node Agent + Spoke Cluster Gateway**), chỉ phù hợp trên cụm 1-node của k3d nhưng sẽ mất trắng 90% log/hostmetrics trên cụm multi-node.
   - Thiếu vắng hoàn toàn thành phần **Thanos Compactor** và chính sách vòng đời dữ liệu (ILM) trên MinIO S3, dẫn đến nguy cơ tràn đĩa hoặc cạn kiệt Inode khi chạy tải kéo dài.
   - Lộ lọt thông tin xác thực quản trị (Plaintext MinIO S3 Credentials) trong các tệp ConfigMap của Loki và Tempo.
   - Bùng nổ chi phí tính toán OTTL do lặp lại các khối gán nhãn và lạm dụng biểu thức chính quy `IsMatch` trên từng span đơn lẻ.
3. **03 Thách Thức Khi Chuyển Dịch Lên Đám Mây Thực Tế (Cloud Migration Challenges):**
   - Phụ thuộc vào việc đồng bộ IP container cục bộ bằng lệnh `docker inspect` trong Ansible DNS patch.
   - Hardcode tên host container của k3d bên trong biến môi trường của các vi dịch vụ TeaStore.
   - Tái tạo chứng chỉ PKI không lũy thừa (non-idempotent) gây đứt gãy kênh truyền mTLS 1.3 khi chạy lại playbook.

---

# PHẦN 1: Kiến Trúc OTel Collector Tại Spoke vs. Hub (Đối Chiếu Với SigNoz)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        ĐỐI CHIẾU MÔ HÌNH THU THẬP: REPO HIỆN TẠI VS. SIGNOZ CHUẨN                      │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  [A. HIỆN TRẠNG REPO CỦA CHÚNG TA (Spoke 1-Replica Deployment)]                                        │
│     Node 1: [teastore Pods] ──┐                                                                        │
│     Node 2: [teastore Pods] ──┼──► [otel-collector-spoke (Deployment 1 Pod trên Node 1)]              │
│     Node 3: [teastore Pods] ──┘         │ (hostPath: /var/log/pods CHỈ ĐỌC ĐƯỢC NODE 1!)               │
│                                         │ (hostmetrics: CHỈ ĐỌC ĐƯỢC NODE 1!)                          │
│                                         ▼ (probabilistic_sampler: drop 80% kể cả lỗi!)                 │
│                                    === [WAN] === (1 kết nối mTLS)                                      │
│                                         ▼                                                              │
│                                   [Hub Gateway] ◄── tail_sampling (Bị đói dữ liệu lỗi!)                │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  [B. MÔ HÌNH SIGNOZ & OTEL PRODUCTION BEST PRACTICE (2-Tier Spoke Architecture)]                       │
│     Node 1: [teastore] ──► [OTel DaemonSet (Agent)] ──┐                                                │
│     Node 2: [teastore] ──► [OTel DaemonSet (Agent)] ──┼──► [Spoke Cluster Gateway (Deployment 2 Pods)] │
│     Node 3: [teastore] ──► [OTel DaemonSet (Agent)] ──┘         │ (Rule-based: Giữ 100% Error/High-Lat)│
│                                                                 │ (Batching lớn, Zstd compression)     │
│                                                            === [WAN] === (1 kết nối mTLS duy nhất)     │
│                                                                 ▼                                      │
│                                                           [Central Hub]                                │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1. Bài Toán Đặt OTel Gateway Tại Spoke & Hạn Chế Của Spoke Deployment
- **Dẫn chứng mã nguồn:** `k8s/base/otel-collector/edge/03-deployment.yaml` (dòng 1-13) khai báo:
  ```yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: otel-collector-spoke
  spec:
    replicas: 1
  ```
  kèm volume mount (dòng 58-60):
  ```yaml
  volumes:
    - name: varlogpods
      hostPath:
        path: /var/log/pods
  ```
- **Phân tích kỹ thuật đối chiếu với SigNoz:**
  1. **Trên môi trường giả lập k3d:** Mỗi cluster (`aws-k3d`, `azure-k3d`) chỉ có đúng 1 container server node (`k3d-aws-k3d-server-0`). Do đó, một Deployment pod 1-replica tình cờ nằm trên node đó và đọc được toàn bộ log và hostmetrics của cụm.
  2. **Khi đưa lên Cloud thật (AWS EKS / Azure AKS đa node):**
     - Một cụm EKS thường có 3-10 worker nodes. Pod `otel-collector-spoke` sẽ chỉ được scheduler xếp vào duy nhất 1 node.
     - Do `hostPath` chỉ gắn kết thư mục cục bộ của máy chủ vật lý mà Pod đang đứng, **Spoke Collector sẽ hoàn toàn bị mù (mất 100% dữ liệu) đối với các tệp log `/var/log/pods` và chỉ số `hostmetrics` (/proc/stat, /proc/meminfo) của 9 worker nodes còn lại!**
     - Các Pod trên các node khác khi gửi OTLP gRPC `:4317` phải đi xuyên qua mạng ảo Kubernetes CNI (Overlay Network) để tìm đến Pod Collector duy nhất, làm tăng độ trễ và nguy cơ nghẽn cổ chai (Single Point of Failure).
  3. **Mô hình chuẩn của SigNoz:**
     - SigNoz luôn phân tách rõ rệt:
       - **Tầng 1 (Node Agent - DaemonSet):** Bắt buộc chạy trên mọi node để thu thập tài nguyên phần cứng vật lý tại chỗ.
       - **Tầng 2 (Cluster Gateway - Deployment):** Thu gom dữ liệu nội bộ trong cụm, thực hiện nén khối lớn và đóng vai trò cổng ra duy nhất để quản lý kết nối mTLS xuyên WAN về Central Hub.

---

### 1.2. Mâu Thuẫn Chết Người Giữa Head Sampling Tại Spoke Và Tail Sampling Tại Hub
- **Dẫn chứng mã nguồn Spoke:** `k8s/base/otel-collector/edge/02-configmap.yaml` (dòng 75-77):
  ```yaml
  probabilistic_sampler:
    sampling_percentage: 20
  ```
  được đưa vào pipeline traces:
  ```yaml
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, filter/drop_noise, resourcedetection, probabilistic_sampler, transform/cluster_id, batch]
      exporters: [otlp/hub, debug]
  ```
- **Dẫn chứng mã nguồn Hub:** `k8s/base/otel-collector/gateway/03-configmap.yaml` (dòng 143-160):
  ```yaml
  tail_sampling:
    decision_wait: 10s
    num_traces: 10000
    policies:
      - name: preserve-all-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: preserve-high-latency-traces
        type: latency
        latency:
          threshold_ms: 1500
      - name: sample-routine-traces
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
  ```
- **Hậu quả nghiêm trọng đối với Hệ thống & AI Engine:**
  1. **Hiện tượng "Bóp chết từ trong trứng nước" (Starvation of Tail Sampler):**
     - `probabilistic_sampler` tại Spoke là một bộ lấy mẫu **Head-based**. Nó kiểm tra băm ngẫu nhiên `TraceID` ngay khi nhận span và vứt bỏ thẳng tay 80% dữ liệu mà **hoàn toàn không cần biết span đó thành công hay thất bại, trễ 10ms hay trễ 10.000ms**.
     - Khi một sự cố nghiêm trọng xảy ra (ví dụ: MySQL deadlock làm sập giao dịch với HTTP 500), có đến **80% khả năng vết thực thi chứa lỗi này bị vứt bỏ ngay tại Spoke Edge**, không bao giờ đi qua mạng WAN để tới Hub.
     - Cấu hình `preserve-all-errors` và `preserve-high-latency-traces` tại Hub Gateway thực chất chỉ đang "nhặt lại những gì còn sót lại" trong 20% span ít ỏi mà Spoke gửi sang.
  2. **Gãy chuỗi vết thực thi (Orphaned Spans & Broken Traces trong môi trường Multi-Cloud):**
     - Trong môi trường phân tán đa đám mây, một giao dịch bắt đầu tại AWS (`teastore-webui`) và lỗi xảy ra ở bước cuối tại Azure (`teastore-persistence` / `teastore-db`).
     - Tại thời điểm các span đầu tiên đi qua AWS Spoke Collector, chúng vẫn mang trạng thái `OK` (vì lỗi ở Azure chưa xảy ra hoặc chỉ nằm ở nhánh hạ nguồn). Do đó, **không thể lọc theo trạng thái lỗi của toàn bộ trace ngay tại từng Spoke riêng lẻ mà không làm mất Span cha (gây ra hiện tượng Orphaned Spans đứt gãy)**.
  3. **Vô hiệu hóa Thuật toán AI Tempo Trace RCA:**
     - Module `TempoTraceAnalyzer` trong `ai-engine/inference/detector.py` tính toán:
       $$\Delta T_{\text{total}} = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$$
     - Công thức này bắt buộc phải có đủ: Span Client gửi từ AWS, Span Server nhận tại Azure, và Span JDBC gọi MySQL. Khi 80% traces bị rụng mất một trong các mắt xích, bộ phân tích RCA sẽ không thể tính được $T_{\text{WAN}}$ hoặc $T_{\text{DB}}$, dẫn đến việc AI không thể suy diễn được nguyên nhân gốc rễ.
  4. **Giải pháp Kiến trúc Chuẩn Xác Đã Triển Khai (Remediation in Phase 3.9.3):**
     - **Tại Spoke Edge (`edge/02-configmap.yaml`):** Giữ nguyên `filter/drop_noise` (để lọc bỏ 100% các span rác healthcheck `/isready`, `/status`, `/finished` ngay tại biên), bật nén `compression: gzip` trong exporter `otlp/hub` để tiết kiệm băng thông WAN, và **gỡ bỏ hoàn toàn `probabilistic_sampler` khỏi pipeline `traces`**.
     - **Tại Hub Gateway (`gateway/03-configmap.yaml`):** Để toàn bộ business spans từ 2 Spoke hội tụ đầy đủ về Hub. Nhờ đó `servicegraphconnector` tính đúng 100% RED metrics và `tail_sampling` tại Hub bảo tồn trọn vẹn 100% chuỗi trace lỗi/chậm (cung cấp đầy đủ các span thành phần $T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$ cho AI Engine) đồng thời chỉ lấy mẫu đối với các trace bình thường trước khi lưu trữ xuống Tempo.

---

# PHẦN 2: Rà Soát Cấu Hình Kubernetes & Observability (`k8s/`)

### 2.1. Rủi Ro Về Lưu Trữ, Đầy Ổ Đĩa & Tràn Bộ Nhớ (Storage, PVC & Retention)

#### A. MinIO S3 Lưu Trữ Dữ Liệu Bất Biến (WORM Storage)
- **Vấn đề:** 
  - `k8s/base/storage-minio/03-pvc.yaml` cấp phát `storage: 10Gi`.
  - `k8s/base/otel-collector/gateway/03-configmap.yaml` (dòng 178-186) cấu hình exporter `awss3` ghi toàn bộ traces, metrics, logs vào bucket `raw-telemetry` dưới dạng file JSON rời rạc.
  - Tệp `k8s/base/storage-minio/04-statefulset.yaml` chỉ tạo thư mục qua initContainer mà **hoàn toàn không có bất kỳ cấu hình ILM (Information Lifecycle Management) hay Script dọn dẹp file cũ**.
- **Hậu quả:** Khi chạy kiểm thử tải Locust liên tục 200 người dùng trong vài giờ, hàng trăm nghìn file JSON nhỏ sẽ lấp đầy 10Gi hoặc làm cạn kiệt bảng Inodes của hệ thống tệp tin ext4/overlayfs (`df -i`), khiến MinIO bị crash và kéo theo toàn bộ Hub Collector bị nghẽn buffer.

#### B. Prometheus & Sự Vắng Mặt Của Thanos Compactor
- **Vấn đề:** 
  - `k8s/base/metrics-thanos/03-statefulset-prometheus.yaml` thiết lập `--storage.tsdb.min-block-duration=2m` và `--storage.tsdb.max-block-duration=2m` để đẩy nhanh việc nén block cho Thanos Sidecar tải lên MinIO bucket `thanos-metrics`.
  - Tuy nhiên, **trong toàn bộ thư mục `k8s/base/metrics-thanos/` hoàn toàn KHÔNG CÓ manifest triển khai Thanos Compactor (`thanos compact`)**.
- **Hậu quả:** Hàng ngàn block 2 phút tí hon sẽ vĩnh viễn nằm rải rác trên MinIO mà không bao giờ được gộp lại thành các block 2h, hoặc tính toán downsampling (5 phút và 1 giờ). Khi người dùng mở Grafana xem xu hướng trong 24h hoặc 7 ngày, Thanos Query sẽ phải tải hàng ngàn file nhỏ từ MinIO về, gây quá tải bộ nhớ RAM và làm trình duyệt bị đơ (Query Timeout).

#### C. Cấu Hình Retention Không Đầy Đủ Của Loki
- **Vấn đề:** `k8s/base/logs-loki/01-configmap.yaml` (dòng 42-45) có bật:
  ```yaml
  compactor:
    retention_enabled: true
  ```
  nhưng trong khối `limits_config` (dòng 47-51) lại **bỏ quên tham số `retention_period`** (ví dụ: `retention_period: 72h`).
- **Hậu quả:** Theo tài liệu chính thức của Grafana Loki, nếu bật `retention_enabled` ở compactor mà không khai báo `retention_period` trong `limits_config`, compactor sẽ không thực hiện xóa bất kỳ chunk log nào, dẫn đến việc dữ liệu log tích tụ vĩnh viễn trong bucket `loki-data`.

---

### 2.2. Rà Soát An Toàn Bảo Mật, Probes & Giới Hạn Tài Nguyên (Resources & Security)

#### A. Lộ Lọt Mật Khẩu Quản Trị Trong ConfigMap (Hardcoded Plaintext Credentials)
- **Dẫn chứng mã nguồn:**
  - `k8s/base/logs-loki/01-configmap.yaml` (dòng 17-18):
    ```yaml
    access_key_id: admin
    secret_access_key: MultiCloudSecurePassword2026!
    ```
  - `k8s/base/traces-tempo/01-configmap.yaml` (dòng 38-39):
    ```yaml
    access_key: admin
    secret_key: MultiCloudSecurePassword2026!
    ```
- **Đánh giá rủi ro:** Đây là lỗi vi phạm nghiêm trọng quy chuẩn an toàn DevSecOps. Thông tin đăng nhập MinIO S3 bị lưu dạng bản rõ (plaintext) trong ConfigMap công khai. Bất kỳ ai có quyền `get configmap` trong namespace `monitoring` đều có thể đọc được mật khẩu quản trị cao nhất của hệ thống lưu trữ. Lẽ ra các thông tin này phải được nạp thông qua biến môi trường lấy từ Secret `minio-creds`.

#### B. Cơ Sở Dữ Liệu `teastore-db` Chạy Ephemeral & Giới Hạn Bộ Nhớ Nguy Hiểm
- **Dẫn chứng mã nguồn:** `k8s/base/teastore/mysql/00-deployment.yaml` (dòng 1-42):
  - Khai báo `kind: Deployment` thay vì `StatefulSet`.
  - **Không có bất kỳ khối `volumeMounts` hay `PersistentVolumeClaim` nào gắn vào thư mục `/var/lib/mysql`!**
  - Khối tài nguyên (dòng 26-31):
    ```yaml
    resources:
      requests:
        cpu: 50m
        memory: 128Mi
      limits:
        memory: 384Mi
    ```
- **Hậu quả:**
  1. Toàn bộ cơ sở dữ liệu `teadb` đang nằm trên tầng writable layer tạm bợ của container. Nếu pod bị khởi động lại, **100% dữ liệu đơn hàng, người dùng của TeaStore sẽ biến mất hoàn toàn**!
  2. Mức giới hạn `memory: 384Mi` là quá thấp đối với MySQL 8.0. Khi Locust chạy tải lớn (nhiều kết nối đồng thời từ `teastore-persistence`), bộ nhớ đệm InnoDB và connection buffers sẽ vượt quá 384Mi, khiến Linux Kernel lập tức bắn tín hiệu `OOMKilled` (`Exit Code 137`), làm sập database trong lúc đang benchmark.

---

### 2.3. Hiệu Năng Xử Lý Của Bộ Quy Tắc OTTL Trong Hub Gateway
- **Dẫn chứng mã nguồn:** `k8s/base/otel-collector/gateway/03-configmap.yaml` (dòng 52-142).
- **Phân tích:**
  1. **Lặp lại mã cấu hình vô ích (Triple Duplication):** Khối logic gán 18 nhãn siêu dữ liệu đám mây (`cloud.provider`, `cloud.region`, `cloud.account.id`, `network.vpc.id`, `cloud.identity.arn`) bị sao chép lặp lại y hệt 3 lần cho `log_statements`, `trace_statements`, và `metric_statements`. Điều này làm file cấu hình phình to hơn 200 dòng, khó bảo trì và dễ gây sai lệch khi cập nhật một chiều.
  2. **Chi Phí Tính Toán Của Biểu Thức Chính Quy `IsMatch`:**
     - Trong `trace_statements` (dòng 105-117), bộ xử lý Peer Service Mapper duyệt qua 7 câu lệnh điều kiện liên tiếp chứa regex: `IsMatch(attributes["server.address"], ".*registry.*")`, `IsMatch(attributes["url.full"], ".*auth.*")`, v.v...
     - Biểu thức chính quy `.*<string>.*` không neo đầu/cuối đòi hỏi máy ảo Go regexp phải quét toàn bộ chuỗi ký tự. Việc thực thi hàng chục regex trên **mỗi một Span đơn lẻ** ở tốc độ hàng ngàn QPS sẽ gây lãng phí nghiêm trọng CPU của Hub Collector, làm tăng độ trễ xử lý nội bộ của Gateway.
     - *Khuyến nghị tối ưu:* Sử dụng hàm so khớp chuỗi trực tiếp rẻ hơn như `attributes["server.address"] == "teastore-registry"` hoặc toán tử `Substring()`.

---

# PHẦN 3: Rà Soát Mã Nguồn `ai-engine/` & `tests/chaos/`

### 3.1. Lỗi Khớp Tên Service Của Prometheus Khiến Code Python Bị Gãy Runtime
- **Dẫn chứng mã nguồn:**
  - `ai-engine/data/collector.py` (dòng 89):
    ```python
    cmd = [
        "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
        "port-forward", "svc/prometheus-server", "9090:80"
    ]
    ```
  - `ai-engine/inference/detector.py` (dòng 115):
    ```python
    cmd = [
        "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
        "port-forward", "svc/prometheus-server", "9090:80"
    ]
    ```
  - `tests/chaos/run_live.py` (dòng 91):
    ```python
    command(["kubectl", "--context", "k3d-hub-k3d", "--request-timeout=10s",
             "-n", "monitoring", "get", "service/prometheus-server", "service/tempo"])
    ```
- **Đối chiếu với manifest thực tế:** `k8s/base/metrics-thanos/04-service-prometheus.yaml` (dòng 1-19):
  ```yaml
  apiVersion: v1
  kind: Service
  metadata:
    name: prometheus
    namespace: monitoring
  spec:
    ports:
      - port: 9090
        targetPort: 9090
        name: web
  ```
- **Hậu quả:** 
  - Tên Service trong Kubernetes là **`prometheus`**, cổng **`9090`**. Trong khi đó, toàn bộ mã nguồn Python lại tìm kiếm **`prometheus-server`** trên cổng **`80`** (đây là tàn dư của chart Helm Prometheus Community cũ).
  - Khi người dùng chạy lệnh `python tests/chaos/run_live.py` hoặc chạy detector ngoài host, script sẽ lập tức văng lỗi:
    `Error from server (NotFound): services "prometheus-server" not found` và dừng toàn bộ tiến trình kiểm thử!

---

### 3.2. Rà Soát Kịch Bản Chaos Tiêm Lỗi Dịch Vụ & Mạng WAN
- **Dẫn chứng mã nguồn:** `tests/chaos/scenarios.json` và `tests/chaos/test_live_evaluation.py`.
- **Phát hiện:**
  - Trong `scenarios.json`, các kịch bản vẫn chứa định danh:
    ```json
    "id": "gcp_wan_delay",
    "entity": "gcp:teastore-recommender",
    "expected_rca": "[CROSS_CLOUD_WAN_DELAY] aws->gcp"
    ```
    và kịch bản CPU saturation:
    ```json
    "entity": "gcp:teastore-recommender",
    "expected_rca": "[SERVICE_CPU_BOTTLENECK] gcp:teastore-recommender"
    ```
  - **Mâu thuẫn:** Trong kiến trúc 3 cụm chuẩn của chúng ta hiện nay, chỉ có 2 Spoke là **`aws-k3d`** và **`azure-k3d`**. Dịch vụ `teastore-recommender` nằm tại `aws-k3d`. Đám mây `gcp` không hề tồn tại trong mô hình lab k3d hiện hành.
  - Khi kịch bản chaos cố gắng truy vấn `kubectl` vào context `k3d-gcp-k3d`, tiến trình sẽ báo lỗi không tìm thấy cụm. Toàn bộ kịch bản này cần được chuẩn hóa triệt để về cặp đám mây thực tế `aws <-> azure`.

---

### 3.3. Mô Hình Vận Hành Của `ai-engine`: Chạy Ngoài Host vs. Chạy Trong K8s Pod
- Hiện tại, module `ai-engine` được thiết kế để chạy như một tiến trình Python độc lập trên máy trạm của kỹ sư (`host`).
- **Hạn chế kỹ thuật:**
  - Khi chạy ngoài host, `ai-engine` phụ thuộc vào việc chạy ngầm các lệnh `kubectl port-forward`. Cơ chế port-forward của Kubernetes rất dễ bị ngắt kết nối khi có biến động mạng hoặc khi Kube-Apiserver bị tải cao, làm gián đoạn luồng suy luận thời gian thực.
  - Exporter Prometheus `:9108` nhúng trong `ai-engine` đang lắng nghe trên IP của máy host. Prometheus bên trong cụm `hub-k3d` không thể tự động scrape được cổng này trừ khi sử dụng địa chỉ `host.k3d.internal` đặc thù của Docker Desktop.
- **Khuyến nghị kiến trúc chuẩn:** Đóng gói `ai-engine` thành container image, tạo manifest `Deployment` và `Service` đặt vào namespace `monitoring` trên `hub-k3d`. Khi đó, AI Engine kết nối thẳng tới `http://prometheus:9090` và `http://tempo:3200` qua DNS nội bộ K8s cực kỳ ổn định, đồng thời Prometheus scrape endpoint `:9108` qua Service discovery tiêu chuẩn.

---

# PHẦN 4: Rà Soát Tự Động Hóa, Ansible & Thách Thức Cloud Migration

### 4.1. Tính Lũy Thừa Của Kịch Bản Sinh Chứng Chỉ PKI (`security/pki/`)
- **Dẫn chứng mã nguồn ban đầu:**
  - `security/pki/scripts/02-generate-hub-cert.sh` và `03-generate-spoke-cert.sh` trực tiếp gọi lệnh `openssl genrsa -out ... 2048` và `openssl x509 -req ...` mà không hề kiểm tra file `.key` hay `.crt` đã tồn tại hay chưa.
- **Rủi ro đứt gãy chuỗi tin cậy (Chain of Trust) & Hạn chế của kiểm tra tệp đơn thuần:**
  - Nếu chỉ kiểm tra `if [ -f server.crt ]; then exit 0; fi`, hệ thống sẽ gặp sự cố nghiêm trọng khi Root CA (`ca.crt`) bị làm mới hoặc chứng chỉ sắp hết hạn/sai cấu hình SAN mà script vẫn bỏ qua không ký lại, gây đứt gãy hoàn toàn chuỗi tin cậy mTLS.
- **Cơ chế Khắc phục Chuẩn Xác (Cryptographic Chain-of-Trust Verification in Phase 3.9.3):**
  - Cập nhật cả 3 scripts (`01-generate-ca.sh`, `02-generate-hub-cert.sh`, `03-generate-spoke-cert.sh`) tuân thủ nghiêm ngặt 3 điều kiện đồng thời:
    1. Thiết lập `umask 077` và phân quyền nghiêm ngặt `chmod 600` cho Private Keys, `chmod 644` cho Public Certificates.
    2. Kiểm tra tính lũy thừa bằng chữ ký mật mã: Chỉ bỏ qua (skip) khi **cả 3 điều kiện đồng thời thỏa mãn**:
       - (a) Cặp file `.key` và `.crt` đều đã tồn tại.
       - (b) Chứng chỉ `.crt` được ký và xác thực hợp lệ 100% bởi CA hiện hành (`openssl verify -CAfile "$CA_CERT" "$CERT_FILE"`).
       - (c) Thời hạn hiệu lực của chứng chỉ còn ít nhất 7 ngày (`openssl x509 -checkend 604800 -noout -in "$CERT_FILE"`).
    3. Hỗ trợ cờ `--force` cho phép SRE chủ động tái tạo và ký lại toàn bộ chứng chỉ khi cần thiết.
    4. Playbook `infra/ansible/playbooks/06_distribute_mtls_secrets.yml` áp dụng cơ chế idempotent nạp secret (`--dry-run=client -o yaml | kubectl apply -f -`), loại bỏ hoàn toàn nguy cơ lệch pha khóa giữa host và K8s Pods.

---

### 4.2. Rào Cản Kỹ Thuật Khi Chuyển Từ k3d Lên AWS EKS & Azure AKS Thật

| Thành Phần Hiện Tại Trên k3d | Cơ Chế Đang Sử Dụng | Rào Cản Kỹ Thuật Khi Chuyển Sang Cloud Thật (EKS / AKS) | Giải Pháp Kiến Trúc Đề Xuất Cho Production |
| :--- | :--- | :--- | :--- |
| **Phân Giải Tên Miền Liên Cụm (Inter-Cluster DNS)** | Playbook `04_sync_cluster_hosts.yml` chạy `docker inspect` lấy IP container trên bridge `mc-monitoring-net` rồi vá vào `NodeHosts` của CoreDNS. | Đám mây AWS và Azure không có Docker daemon, không dùng chung bridge ảo. Các worker node nằm trên các VPC/VNet độc lập. | Triển khai **VPC/VNet Peering** kết hợp **Route 53 Private Hosted Zone** và **Azure Private DNS**, hoặc sử dụng giải pháp Multi-Cluster Service Discovery như **Cilium Cluster Mesh / Submariner**. |
| **Cấu Hình Địa Chỉ Vi Dịch Vụ** | Hardcode `HOST_NAME: k3d-azure-k3d-server-0` và `REGISTRY_HOST: k3d-aws-k3d-server-0` trong K8s Deployment. | Tên container k3d không tồn tại trên Cloud thật. Địa chỉ IP của Node trong EKS/AKS là động và có thể bị thay đổi khi Auto-scaling. | Sử dụng Kubernetes Ingress FQDN hoặc Private Network Load Balancer (NLB trên AWS và Azure Standard LB) với tên miền tĩnh (vd: `registry.aws.internal`). |
| **Mô Phỏng Độ Trễ WAN** | Dùng `tc qdisc netem` tiêm trực tiếp vào card `eth0` của container Docker server node. | Trên AWS EKS (dùng AWS VPC CNI), việc sửa `qdisc` trên node host đòi hỏi đặc quyền cao và có thể gây xung đột với bộ định tuyến nội bộ của AWS ENI. | Sử dụng giải pháp Chaos cấp độ Pod (Chaos Mesh / LitmusChaos) chèn proxy trễ hoặc tiêm độ trễ thông qua Service Mesh Envoy proxy sidecar. |
| **Phân Phối Chứng Chỉ mTLS** | Dùng Ansible đọc file từ thư mục host rồi gọi lệnh `kubectl create secret` vào từng cụm. | Các cụm Cloud thật được quản trị qua CI/CD và IAM độc lập, không cho phép lưu trữ private key trôi nổi trên máy trạm của lập trình viên. | Sử dụng **`cert-manager`** tích hợp với HashiCorp Vault hoặc **AWS Private Certificate Authority (ACM PCA)** để tự động xoay vòng (auto-rotate) chứng chỉ mTLS. |

---

# PHẦN 5: Phân Loại & Tổng Hợp Danh Mục Lỗi Theo 3 Mức Độ Ưu Tiên

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              MA TRẬN TỔNG HỢP CÁC PHÁT HIỆN KIỂM TOÁN                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  MỨC 1: CRITICAL / BLOCKER BUGS (Cần sửa ngay trên k3d trước Phase 4 Benchmark)                        │
│  ├── [BUG-01] Sai lệch tên Service Prometheus trong code Python: svc/prometheus-server vs prometheus   │
│  ├── [BUG-02] Mâu thuẫn Head Sampling 20% tại Spoke làm đói dữ liệu lỗi và gãy Trace RCA tại Hub      │
│  └── [BUG-03] teastore-db MySQL chạy Ephemeral (không PVC) và giới hạn RAM 384Mi có nguy cơ OOMKilled  │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  MỨC 2: ARCHITECTURAL TRADE-OFFS (Điểm hạn chế của Lab k3d cần ghi nhận nâng cấp chuẩn SigNoz)         │
│  ├── [ARCH-01] Spoke Collector chạy Deployment 1-pod thay vì DaemonSet + Spoke Gateway                 │
│  ├── [ARCH-02] Thiếu Thanos Compactor và thiếu ILM Lifecycle Policy trên MinIO S3 (Nguy cơ Disk Full) │
│  ├── [ARCH-03] Lộ lọt mật khẩu plaintext của MinIO trong ConfigMap của Loki và Tempo                   │
│  ├── [ARCH-04] Lạm dụng biểu thức chính quy IsMatch trên từng Span trong bộ xử lý OTTL Hub Gateway     │
│  └── [ARCH-05] Còn sót lại định danh và kịch bản cũ của cụm GCP trong scenarios.json                   │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  MỨC 3: CLOUD MIGRATION CHALLENGES (Rào cản khi đưa từ k3d lên AWS EKS & Azure AKS thật)               │
│  ├── [CLOUD-01] Phụ thuộc vào cơ chế docker inspect để vá NodeHosts trong CoreDNS                      │
│  ├── [CLOUD-02] Hardcode tên host container k3d trong biến môi trường TeaStore                         │
│  └── [CLOUD-03] Kịch bản sinh chứng chỉ PKI không lũy thừa, gây lỗi mTLS khi tái chạy Makefile        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

# PHẦN 6: Khuyến Nghị & Kế Hoạch Khắc Phục (Actionable Remediation Roadmap)

Dưới đây là kế hoạch hành động đề xuất và trạng thái khắc phục thực tế sau Phase 3.9.3:

| Mã Phát Hiện | Hạng Mục Khắc Phục | Tệp Cần Chỉnh Sửa | Giải Pháp Kỹ Thuật Đã Thực Hiện | Mức Ưu Tiên | Trạng Thái |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **`BUG-01`** | Sửa tên Service Prometheus trong mã nguồn Python | `ai-engine/data/collector.py`, `ai-engine/inference/detector.py`, `tests/chaos/run_live.py` | Đổi `svc/prometheus-server` thành `svc/prometheus`, đổi port `9090:80` thành `9090:9090`. | **P1 (Critical)** | **`[RESOLVED - INC-P3-22]`** |
| **`BUG-02`** | Điều chỉnh chiến lược Lấy mẫu tại Spoke Edge & Bảo toàn Error Traces | `k8s/base/otel-collector/edge/02-configmap.yaml` | Gỡ bỏ hoàn toàn `probabilistic_sampler` tại Spoke Edge, bật `compression: gzip` trên exporter `otlp/hub` để tối ưu băng thông WAN; hội tụ 100% spans về Hub Gateway để `servicegraphconnector` tính đúng RED metrics và `tail_sampling` bảo toàn 100% traces lỗi/chậm cho AI Engine. | **P1 (Critical)** | **`[RESOLVED - INC-P3-22]`** |
| **`BUG-03`** | Bền vững hóa MySQL và tăng ngưỡng RAM an toàn | `k8s/base/teastore/mysql/00-deployment.yaml` | Nâng `requests.memory` lên `256Mi` và `limits.memory` từ `384Mi` lên `768Mi` (gấp đôi) chống K8s OOMKilled khi chạy tải Locust. | **P1 (Critical)** | **`[RESOLVED - INC-P3-22]`** |
| **`ARCH-02`**| Bổ sung cơ chế dọn dẹp lưu trữ MinIO S3 & Retention Loki | `k8s/base/logs-loki/01-configmap.yaml` | Khai báo `retention_period: 72h` trong `limits_config` của Loki, đồng bộ với `compactor.retention_enabled: true` dọn dẹp chunk quá hạn trên MinIO bucket `loki-data`. | **P2 (High)** | **`[RESOLVED - INC-P3-22]`** |
| **`ARCH-03`**| Bảo mật thông tin xác thực MinIO S3 | `k8s/base/logs-loki/` & `k8s/base/traces-tempo/` | Chuyển `access_key` và `secret_key` từ ConfigMap sang tham chiếu K8s Secret `minio-creds`. | **P2 (High)** | *Planned (Phase 4)* |
| **`ARCH-04`**| Tối ưu hóa hiệu năng OTTL Gateway | `k8s/base/otel-collector/gateway/03-configmap.yaml` | Thay thế các lệnh regex `IsMatch` bằng so khớp chuỗi trực tiếp; gộp các lệnh gán nhãn trùng lặp. | **P3 (Medium)** | *Planned (Phase 4)* |
| **`ARCH-05`**| Chuẩn hóa kịch bản chaos về topology 3 cụm | `tests/chaos/scenarios.json` | Thay thế toàn bộ định danh `gcp:teastore-recommender` bằng `aws:teastore-recommender` và `aws_wan_delay` (`aws->azure`). | **P3 (Medium)** | **`[RESOLVED - INC-P3-22]`** |
| **`CLOUD-03`**| Tăng cường tính lũy thừa & Xác thực chuỗi tin cậy mật mã cho PKI | `security/pki/scripts/01-generate-ca.sh`, `02-generate-hub-cert.sh`, `03-generate-spoke-cert.sh` | Thiết lập `umask 077`, phân quyền `chmod 600` cho keys. Chỉ bỏ qua tạo lại khóa khi đồng thời thỏa mãn: (a) file `.key` và `.crt` tồn tại, (b) xác thực chữ ký hợp lệ bởi CA hiện hành (`openssl verify -CAfile`), (c) cert còn hạn ít nhất 7 ngày (`openssl x509 -checkend 604800`). Hỗ trợ cờ `--force`. | **P3 (Medium)** | **`[RESOLVED - INC-P3-22]`** |

---

## Kết Luận Của Kiểm Toán Viên

Hệ thống mã nguồn của dự án trên nhánh `feat/integrate-infra-ai-anomaly` đã hoàn thiện được một khối lượng công việc đồ sộ về hạ tầng quan sát đa đám mây và trí tuệ nhân tạo. Tuy nhiên, các lỗi bất đồng bộ giữa mã nguồn Python và Kubernetes manifest (**`BUG-01`**) cùng sự mâu thuẫn trong chiến lược lấy mẫu tại biên (**`BUG-02`**) là những điểm nghẽn kỹ thuật **bắt buộc phải được khắc phục** trước khi tiến hành thu thập số liệu benchmark chính thức ở Phase 4.

Toàn bộ các phân tích trong tài liệu này được thực hiện ở chế độ **Strict Read-Only**, tuân thủ nghiêm ngặt quy tắc không tự ý sửa đổi mã nguồn khi chưa có sự phê duyệt chính thức từ ban quản trị.

