# Architecture Decision Records (ADR) — Multi-Cloud Observability & AIOps

Tài liệu này tổng hợp **12 Quyết định Kiến trúc Chuẩn tắc (12 Canonical ADRs)** cho hệ thống **Multi-Cloud Observability & AIOps** với ứng dụng kiểm thử chuẩn **SPEC RG TeaStore** trên mô hình 3 cụm Kubernetes (`hub-k3d`, `aws-k3d`, `azure-k3d`).

Sau quá trình tinh gọn và chuẩn hóa kiến trúc (Architecture Consolidation), toàn bộ 21 bản ghi ADR cũ và 17 bản đặc tả kỹ thuật phân mảnh (SPEC-0001 đến SPEC-0017) đã được hợp nhất toàn diện vào 12 Canonical ADRs dưới đây. Mọi công thức định lượng PromQL, vòng đời lưu trữ (retention periods), tham số mô phỏng mạng WAN và cấu hình an ninh Zero-Trust đều được nhúng trực tiếp vào các quyết định kiến trúc tương ứng, đảm bảo tính nguyên vẹn và khả năng truy xuất nguồn gốc tuyệt đối.

---

## 1. Danh mục 12 Quyết định Kiến trúc Chuẩn tắc (12 Canonical ADRs)

| Mã ADR | Tiêu đề Kiến trúc | Trạng thái | Phân nhóm Chức năng |
| :--- | :--- | :--- | :--- |
| [ADR-0001](./ADR-0001-multi-cluster-topology-wan.md) | Multi-Cluster Hub-Spoke Topology & WAN Network Emulation | Implemented | Infrastructure & Network |
| [ADR-0002](./ADR-0002-kyverno-policy-as-code.md) | Kyverno Policy-as-Code & Supply Chain Security Governance | Implemented | DevSecOps & Compliance |
| [ADR-0003](./ADR-0003-zero-trust-pki-mtls.md) | Zero-Trust PKI Infrastructure, Cross-Cluster mTLS 1.3 & Secret Encryption | Implemented | Security & Zero-Trust |
| [ADR-0004](./ADR-0004-multicluster-gitops-argocd.md) | Centralized Multi-Cluster GitOps Delivery with Argo CD & Canary Rollouts | Implemented | GitOps & Delivery |
| [ADR-0005](./ADR-0005-slo-management-smart-alerting.md) | SLO-as-Code Governance, Multi-Burn-Rate Alerting & Robusta Remediation | Implemented | SRE & Smart Alerting |
| [ADR-0006](./ADR-0006-opentelemetry-pipeline-processing.md) | OpenTelemetry End-to-End Pipeline, Edge Filtering & Semantic Normalization | Implemented | Telemetry & Processing |
| [ADR-0007](./ADR-0007-tiered-storage-thanos-loki-tempo.md) | Multi-Cloud Observability Storage Engine: Thanos, Loki, Tempo & MinIO S3 | Implemented | Storage & Query Federation |
| [ADR-0008](./ADR-0008-teastore-benchmark-workload.md) | TeaStore Microservice Benchmark Architecture & Locust Workload Modeling | Implemented | Benchmark & Workloads |
| [ADR-0009](./ADR-0009-chaos-fault-injection.md) | Chaos Engineering Framework, Fault Injection Matrix & Quantitative Validation | Implemented | Chaos & Reliability |
| [ADR-0010](./ADR-0010-telemetry-cost-finops.md) | Multi-Cloud Telemetry FinOps Governance & WAN Egress Cost Optimization | Implemented | FinOps & Economics |
| [ADR-0011](./ADR-0011-ai-anomaly-detection-rca.md) | Closed-Loop AI Anomaly Detection Engine & Distributed Trace RCA | Implemented | AIOps & Intelligence |
| [ADR-0012](./ADR-0012-folder-over-branch-gitops-layout.md) | Folder-Over-Branch GitOps Layout & Declarative Manifest Hygiene | Implemented | Repository & Manifest Hygiene |

---

## 2. Bảng Ánh Xạ Truy Xuất Nguồn Gốc (Traceability Matrix)

Bảng dưới đây thiết lập mối quan hệ truy xuất nguồn gốc 1:1 và 1:N giữa 21 ADR tiền nhiệm, 17 Technical SPECs cũ và 12 Canonical ADRs mới:

| Canonical ADR Hiện tại | ADR Tiền nhiệm Hợp nhất | SPEC Tiền nhiệm Hợp nhất | Nội dung Định lượng và Chuẩn hóa Tích hợp |
| :--- | :--- | :--- | :--- |
| **ADR-0001** (Multi-Cluster Topology & WAN) | ADR-0001, ADR-0002, ADR-0003 | SPEC-0001, SPEC-0002 | Subnet Docker `172.28.0.0/16`, địa chỉ IP tĩnh Node k3d (`172.28.0.2`–`4`), CoreDNS NodeHosts (`hub.local`, `aws.local`, `azure.local`), tham số suy giảm mạng `tc netem` (10ms delay, 2ms jitter, 0.1% loss), ngân sách tài nguyên 8–10 GB RAM. |
| **ADR-0002** (Kyverno Policy-as-Code) | ADR-0004, ADR-0005 | SPEC-0004, SPEC-0005 | Kyverno ClusterPolicies (`deploy/policies/`), chế độ Enforce/Fail-Closed, kiểm thử Shift-Left `kyverno test`, cấm tag `:latest`, bắt buộc `readOnlyRootFilesystem: true`, loại bỏ `ALL` capabilities, xác thực chữ ký số Sigstore Cosign và SLSA Build L2. |
| **ADR-0003** (Zero-Trust PKI & mTLS 1.3) | ADR-0006, ADR-0007, ADR-0008 | SPEC-0006, SPEC-0007, SPEC-0008 | Kiến trúc PKI với cert-manager (Root CA, Intermediate CA, SANs `*.hub.local`, `otel-gateway...`), giao thức mTLS 1.3 gốc trong OTel Collector (Cipher suites `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`), thời hạn chứng chỉ 90 ngày với tự động gia hạn trước 30 ngày, mã hóa bất đối xứng GitOps với Bitnami Sealed Secrets. |
| **ADR-0004** (Multi-Cluster GitOps & Canary) | ADR-0009, ADR-0010 | SPEC-0003, SPEC-0009 | Quản trị tập trung với Argo CD trên `hub-k3d`, đồng bộ đa cụm bằng ApplicationSets (List/Matrix Generators), Sync Waves (0 đến 3), triển khai luân phiên Argo Rollouts với AnalysisTemplate phân tích độ trễ P99 < 500ms và tỷ lệ lỗi 5xx < 1%, tự động quay lui (auto-rollback). |
| **ADR-0005** (SLO Governance & Robusta) | ADR-0010, ADR-0011 | SPEC-0010, SPEC-0011 | Quản trị SLO-as-Code với Pyrra qua `ServiceLevelObjective` CRDs, luật cảnh báo Google SRE Multi-Window Multi-Burn-Rate (1h/5% burn, 6h/10% burn, 3d/2% burn), Robusta Runner làm giàu ngữ cảnh cảnh báo (log 50 dòng, K8s events), định tuyến Telegram sink với bộ đệm hạ nhiệt 60s cooldown buffer. |
| **ADR-0006** (OpenTelemetry Pipeline) | ADR-0012, ADR-0013, ADR-0014 | SPEC-0012, SPEC-0013, SPEC-0014 | Thu thập không xâm lấn với OTel Operator & Javaagent bytecode, pipeline processor chuẩn (`memory_limiter` $\rightarrow$ `filter` $\rightarrow$ `transform` $\rightarrow$ `batch` $\rightarrow$ `exporter`), lọc nhiễu biên `filter/drop_noise` (bỏ probes `/health`, `/ready`), lấy mẫu 20% head sampling tại biên, tail sampling tập trung tại Hub (100% lỗi và độ trễ > 1500ms), chuẩn hóa OTTL Semantic Conventions, tiền tổng hợp Service Graph `traces_service_graph_request_total`. |
| **ADR-0007** (Tiered Storage: Thanos, Loki, Tempo) | ADR-0015, ADR-0016, ADR-0017 | SPEC-0015, SPEC-0016, SPEC-0017 | Lưu trữ phân tầng với MinIO S3 buckets (`thanos-data`, `loki-data`, `tempo-data`), TSDB hot storage 2h (`2h`), Thanos Compactor downsampling (5m sau 40h, 1h sau 10d), chính sách lưu trữ (raw: 30d, 5m: 90d, 1h: 365d), Grafana Loki retention (7d), Grafana Tempo trace retention (7d), Thanos Query liên cụm, tự động hóa dashboard với Grafana Sidecar. |
| **ADR-0008** (TeaStore Benchmark & Locust) | ADR-0018 | *N/A* (Kế thừa từ ADR-0018) | Phân vùng microservice TeaStore: tầng tính toán (`webui`, `auth`, `recommender`, `image`, `registry`) trên `aws-k3d`, tầng lưu trữ (`persistence`, MySQL `teastore-db`) trên `azure-k3d`, bộ sinh tải Locust không giao diện (`locustfile.py`), các mẫu tải mua sắm (browse, cart, checkout), baseline hiệu năng. |
| **ADR-0009** (Chaos Fault Injection Matrix) | ADR-0019 | *N/A* (Kế thừa từ ADR-0019) | Khung thử nghiệm hỗn loạn 4 kịch bản (CHAOS-01: suy giảm WAN qua `tc netem`, CHAOS-02: dừng pod/service crash, CHAOS-03: khóa DB & độ trễ MySQL, CHAOS-04: nghẽn CPU/Memory), phương pháp kiểm định giả thuyết SRE, đo lường định lượng MTTD, MTTR và đánh giá tỷ lệ burn rate. |
| **ADR-0010** (Telemetry FinOps & Egress) | ADR-0020 | *N/A* (Kế thừa từ ADR-0020) | Mô hình chi phí mạng WAN egress đa đám mây ($0.08–$0.12/GB), đánh giá ROI từ việc lọc nhiễu tại biên (cắt giảm 60–80% lưu lượng raw probes), tối ưu hóa lưu trữ phân tầng S3 so với SSD (~70% tiết kiệm), nén dữ liệu OTLP gRPC. |
| **ADR-0011** (AI Anomaly Detection & Trace RCA) | ADR-0021 | *N/A* (Kế thừa từ AI V3 Architecture) | Động cơ AIOps Ensemble kết hợp GRU Autoencoder, Temporal Convolutional Network (TCN) và Isolation Forest, trích xuất đặc trưng chuỗi thời gian qua PromQL, phân rã vết giao dịch distributed trace RCA ($T_{\text{total}} = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$), HTTP Exporter trên cổng `:9108`, Grafana Panel 7 Dual Y-Axis, cảnh báo Telegram khép kín với 60s cooldown buffer. |
| **ADR-0012** (Folder-Over-Branch GitOps Layout) | *ADR-012 Upstream* & ADR-0001 | SPEC-0001 | Bố cục thư mục Folder-Over-Branch GitOps trên nhánh đơn `main`, loại bỏ phân nhánh theo môi trường, phân vùng chức năng (`deploy/platform/`, `deploy/workloads/`, `deploy/policies/`, `deploy/integrations/`, `deploy/argocd/`, `deploy/clusters/`), nguyên tắc Single Responsibility Principle (SRP) cho manifest (tiền tố `00-` đến `07-`), tách biệt con trỏ `release-images.yaml` khỏi cấu hình vận hành để triệt tiêu merge conflicts. |

---

## 3. Quy tắc Quản lý và Thay đổi Kiến trúc (ADR Evolution Rules)
1. Mọi quyết định thay đổi cấu hình kỹ thuật, công nghệ nền tảng hoặc điều chỉnh tham số SLO/FinOps/AIOps đều phải được cập nhật trực tiếp vào 12 Canonical ADRs tương ứng.
2. Trạng thái vòng đời của ADR tuân thủ: `Proposed` $\rightarrow$ `In-Progress` $\rightarrow$ `Implemented` $\rightarrow$ `Verified` $\rightarrow$ `Superseded`.
3. Bất kỳ manifest Kubernetes nào dưới `deploy/` hoặc kịch bản hạ tầng dưới `infra/` đều phải tìm thấy cơ sở lý luận trong các ADRs này.
