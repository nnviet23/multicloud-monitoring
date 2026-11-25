# 12 Quyết định Kiến trúc (Canonical ADRs) — Multi-Cloud Observability & Closed-Loop AIOps

> Tài liệu này mô tả hệ thống **hoạt động như thế nào**, **luồng viễn trắc vận hành ra sao**, và **vì sao lại bảo mật, tối ưu chi phí**. Chi tiết lý do và bối cảnh kỹ thuật cho từng quyết định thiết kế nằm trong [12 Quyết định Kiến trúc (Canonical ADRs)](adr/README.md).

---

## 1. Thành phần Hệ thống (System Components)

Hệ thống được thiết kế theo mô hình **Hub-Spoke** gồm 3 cụm Kubernetes k3d cục bộ (được điều phối tự động qua Python Platform CLI `infra.cli` và Makefile):

| Thành phần | Cụm / Vị trí | Công nghệ & Phiên bản | Vai trò & Liên kết ADR |
| :--- | :--- | :--- | :--- |
| **TeaStore Compute** | `aws-k3d` (Spoke 1) | Java 11 Tomcat (`webui`, `auth`, `recommender`, `image`, `registry`) | Lớp dịch vụ tính toán của ứng dụng kiểm thử chuẩn ([ADR-0008](adr/ADR-0008-teastore-benchmark-workload.md)) |
| **TeaStore Data** | `azure-k3d` (Spoke 2) | Java 11 JPA (`persistence`), TeaStore DB (`teastore-db:1.4.1`) | Lớp lưu trữ dữ liệu bền vững và cơ sở dữ liệu quan hệ ([ADR-0008](adr/ADR-0008-teastore-benchmark-workload.md)) |
| **OTel Java Agent** | Cả 2 Spoke | `opentelemetry-javaagent:v2.10.0` | Tự động đo đạc bytecode không xâm lấn mã nguồn ([ADR-0006](adr/ADR-0006-opentelemetry-pipeline-processing.md)) |
| **Locust Generator** | Ngoài cụm / Host | Python `locustio/locust:2.24.0` | Sinh tải người dùng mô phỏng hành vi mua sắm e-commerce ([ADR-0008](adr/ADR-0008-teastore-benchmark-workload.md)) |
| **Spoke OTel Collector** | `aws-k3d`, `azure-k3d` | `otel/opentelemetry-collector-contrib:0.114.0` | Thu thập metrics/logs/traces tại biên, lọc rác probe qua WAN ([ADR-0006](adr/ADR-0006-opentelemetry-pipeline-processing.md)) |
| **WAN Network Bridge** | Docker Network | Linux Kernel `tc netem` | Giả lập suy hao mạng diện rộng liên vùng (RTT $10\text{ ms} \pm 2\text{ ms}$, loss $0.1\%$) ([ADR-0001](adr/ADR-0001-multi-cluster-topology-wan.md)) |
| **Native mTLS 1.3** | Đường truyền gRPC | Go `crypto/tls` (TLS 1.3) | Bảo mật đường truyền OTLP `:4317` xuyên đám mây, loại bỏ reverse proxy ([ADR-0003](adr/ADR-0003-zero-trust-pki-mtls.md)) |
| **Hub OTel Gateway** | `hub-k3d` (Central) | `otel/opentelemetry-collector-contrib:0.114.0` | Chuẩn hóa OTTL, tổng hợp đồ thị Topology, lấy mẫu đuôi Tail Sampling ([ADR-0006](adr/ADR-0006-opentelemetry-pipeline-processing.md)) |
| **Thanos Suite** | `hub-k3d` (Central) | `quay.io/thanos/thanos:v0.36.1` (Prometheus + Thanos Sidecar, Query, Store, Compact) | Tiếp nhận TSDB nóng, truy vấn hợp nhất toàn cầu và đánh giá cảnh báo ([ADR-0007](adr/ADR-0007-tiered-storage-thanos-loki-tempo.md)) |
| **Grafana Loki** | `hub-k3d` (Central) | `grafana/loki:2.9.4` | Lưu trữ và lập chỉ mục nhật ký phân tán (Distributed Logs) ([ADR-0007](adr/ADR-0007-tiered-storage-thanos-loki-tempo.md)) |
| **Grafana Tempo** | `hub-k3d` (Central) | `grafana/tempo:2.4.0` | Lưu trữ vết phân tán dung lượng lớn (Distributed Traces) ([ADR-0007](adr/ADR-0007-tiered-storage-thanos-loki-tempo.md)) |
| **MinIO S3** | `hub-k3d` (Central) | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | Kho lưu trữ đối tượng lạnh phân tầng (Metrics, Logs, Traces) ([ADR-0007](adr/ADR-0007-tiered-storage-thanos-loki-tempo.md)) |
| **Grafana + Sidecar** | `hub-k3d` (Central) | `grafana/grafana:11.5.0` | 10 Dashboards SRE giám sát chuẩn USE/RED, Dual Y-Axis ([ADR-0007](adr/ADR-0007-tiered-storage-thanos-loki-tempo.md)) |
| **Pyrra (SLO-as-Code)** | `hub-k3d` (Central) | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Tự động sinh PromQL Burn Rate cảnh báo vi phạm Error Budget ([ADR-0005](adr/ADR-0005-slo-management-smart-alerting.md)) |
| **Robusta Runner** | `hub-k3d` (Central) | `robustadev/robusta-runner:0.53.0` | Làm giàu ngữ cảnh cảnh báo 4W, tự động sửa lỗi qua GitHub Actions ([ADR-0005](adr/ADR-0005-slo-management-smart-alerting.md)) |
| **AI Anomaly Engine V3**| Host / Container | PyTorch 2.1+, Scikit-Learn | Deep Ensemble (GRU + TCN + Isolation Forest), Tempo Trace RCA, Exporter :9108 ([ADR-0011](adr/ADR-0011-ai-anomaly-detection-rca.md)) |

---

## 2. Mô hình Tô-pô & Luồng Dữ liệu Liên Cụm (Multi-Cluster Topology)

```mermaid
flowchart TD
    subgraph SpokeAWS["Spoke 1 — aws-k3d (Compute Simulation)"]
        TS_UI["TeaStore WebUI / Auth / Rec / Image"]
        LOCUST["Locust Workload Generator"] --> TS_UI
        JAVA_AGENT1["OTel Java Agent (Bytecode)"] -.-> TS_UI
        TS_UI -->|Internal OTLP| EDGE_OTEL1["OTel Edge Collector<br/>(Drop Health Probes / Filter Noise)"]
    end

    subgraph SpokeAzure["Spoke 2 — azure-k3d (Data Simulation)"]
        TS_DATA["TeaStore Persistence (Hibernate JPA)"]
        MYSQL[("TeaStore DB (teastore-db:1.4.1)")]
        TS_DATA --> MYSQL
        JAVA_AGENT2["OTel Java Agent (Bytecode)"] -.-> TS_DATA
        TS_DATA -->|Internal OTLP| EDGE_OTEL2["OTel Edge Collector<br/>(MySQL Receiver + App Traces)"]
    end

    subgraph WANBridge["Mạng diện rộng giả lập (WAN Bridge: 172.28.0.0/16)"]
        NETEM["tc netem: RTT 10ms ± 2ms, Loss 0.1%<br/>Native mTLS 1.3 (gRPC :4317)"]
    end

    EDGE_OTEL1 ==>|mTLS 1.3 WAN| NETEM
    EDGE_OTEL2 ==>|mTLS 1.3 WAN| NETEM

    subgraph CentralHub["Central Hub — hub-k3d (Observability & Control)"]
        NETEM ==>|mTLS 1.3| HUB_GW["Hub OTel Gateway (:4317)<br/>• OTTL Normalization<br/>• Tail Sampling (100% Error, Latency>1500ms)<br/>• Service Graph Topology Aggregation"]
        
        HUB_GW -->|Metrics| THANOS_RCV["Thanos Receive (:19291)"]
        HUB_GW -->|Logs| LOKI["Grafana Loki (:3100)"]
        HUB_GW -->|Traces| TEMPO["Grafana Tempo (:4317)"]
        
        THANOS_RCV -->|Cold TSDB Blocks| MINIO[("MinIO S3 Object Storage")]
        LOKI -->|Cold Chunks| MINIO
        TEMPO -->|Cold Trace Blocks| MINIO

        THANOS_QUERY["Thanos Query (:9090)"] --> THANOS_RCV
        THANOS_RULER["Thanos Ruler"] --> THANOS_QUERY
        PYRRA["Pyrra SLO-as-Code"] --> THANOS_QUERY

        GRAFANA["Grafana (:3000)<br/>8 SRE Dashboards"] --> THANOS_QUERY
        GRAFANA --> LOKI
        GRAFANA --> TEMPO

        ALERTMGR["Alertmanager (:9093)"] --> ROBUSTA["Robusta Runner (:5000)<br/>4W Enrichment (Logs, Events, Graph)"]
        THANOS_RULER --> ALERTMGR
        ROBUSTA --> TELEGRAM["Telegram Alert Sink"]
    end

    subgraph AIOpsEcosystem["Động cơ Trí tuệ Nhân tạo AIOps V3"]
        AI_ENGINE["AI Anomaly Detection Engine V3<br/>• PromQL 8 Features (15s poller)<br/>• GRU + TCN + Isolation Forest<br/>• Tempo Trace RCA (T_WAN, T_self, T_DB)"]
        AI_ENGINE <-->|PromQL Query| THANOS_QUERY
        AI_ENGINE <-->|Trace RCA| TEMPO
        AI_ENGINE -->|Metrics Exporter :9108| THANOS_RCV
        AI_ENGINE -->|Direct Alerts (Cooldown 60s)| TELEGRAM
    end
```

---

## 3. Kiến trúc Bảo mật & Nguyên tắc Vận hành (Security & Principles)

Hệ thống được bảo vệ bằng mô hình **Zero-Trust Network & DevSecOps** với 5 nguyên tắc cốt lõi:

1. **Native mTLS 1.3 Xuyên Biên giới Đám mây ([ADR-0003](adr/ADR-0003-zero-trust-pki-mtls.md)):**
   - Lưu lượng OTLP đi qua mạng công cộng giả lập được mã hóa bằng chứng chỉ x509 hai chiều (Client Certificate Authentication) sinh qua `python -m infra.cli certs`.
   - Loại bỏ hoàn toàn Reverse Proxy L7 (như Traefik hay NGINX) ở giữa để tránh TLS Termination, tiết kiệm 150–300 MB RAM cho cụm Hub và bảo đảm mã hóa đầu cuối thực sự.
2. **Kiểm soát Bí mật Tập trung (Zero Plaintext Secrets - [ADR-0003](adr/ADR-0003-zero-trust-pki-mtls.md)):**
   - Toàn bộ mật khẩu, API token, access keys được gom vào tệp biến môi trường `.env` duy nhất (được đưa vào `.gitignore`).
   - Manifests K8s sử dụng `kustomize secretGenerator` để tạo động Secret trên cụm; phân chia đặc quyền tài khoản S3 độc lập (`thanos-s3-creds` tách rời `otel-s3-creds`).
3. **Nguyên tắc Đơn nhiệm Manifests (Single Responsibility Principle - SRP):**
   - Mỗi file manifest chỉ định nghĩa duy nhất 1 loại tài nguyên Kubernetes, có tiền tố thứ tự nạp: `00-namespace.yaml`, `01-secret.yaml`, `02-configmap.yaml`, `03-pvc.yaml`, `04-statefulset.yaml`, `05-service.yaml` ([ADR-0012](adr/ADR-0012-folder-over-branch-gitops-layout.md)).
4. **Ghim Cứng Phiên bản Tuyệt đối (Strict Version Pinning - [ADR-0002](adr/ADR-0002-kyverno-policy-as-code.md)):**
   - Tuyệt đối cấm sử dụng tag trôi nổi (`latest`, `master`). Toàn bộ container images đều có phiên bản cụ thể cố định trong `infra/README.md`.
5. **Tiền Lọc Nhiễu tại Biên & Lấy Mẫu Đuôi tại Trung tâm ([ADR-0006](adr/ADR-0006-opentelemetry-pipeline-processing.md)):**
   - Spoke Collector loại bỏ 100% health checks (`/healthz`, `/readyz`) trước khi dữ liệu đi vào WAN, tiết kiệm 35–45% băng thông mạng liên vùng.
   - Hub Gateway áp dụng `tail_sampling` giữ lại 100% trace lỗi (HTTP 5xx) và trace có độ trễ cao (>1500ms), bảo đảm khả năng điều tra sự cố mà không gây quá tải bộ nhớ TSDB.

---

## 4. Ngân sách Tài nguyên Máy trạm (Resource Budget: 8–10 GB RAM)

Hệ thống được cân chỉnh tối ưu để vận hành mượt mà trên môi trường máy trạm cá nhân:

| Cụm / Thành phần | Các tiến trình chính | Ước tính RAM |
| :--- | :--- | :---: |
| **`hub-k3d`** | K3s control plane, OTel Gateway, Prometheus + Thanos (Sidecar, Query, Store, Compact), Loki, Tempo, MinIO, Grafana, Pyrra, Alertmanager, Robusta Runner | **~4.2 – 5.2 GB** |
| **`aws-k3d`** | K3s control plane, TeaStore 5 compute services + Java Agent, Spoke OTel Collector | **~2.2 – 2.8 GB** |
| **`azure-k3d`** | K3s control plane, TeaStore Persistence + Java Agent, TeaStore DB (`teastore-db:1.4.1`), Spoke OTel Collector | **~1.3 – 1.7 GB** |
| **Host Components** | Locust load generator, AI Anomaly Engine V3 (PyTorch inference via `infra.cli`) | **~0.8 – 1.2 GB** |
| **TỔNG CỘNG** | **Toàn bộ nền tảng Multi-Cloud Observability & Closed-Loop AIOps** | **~8.5 – 9.8 GB** |
