# Phân tích Hệ thống & Báo cáo Audit: Multi-Cloud Observability & AIOps Platform

Tài liệu này tổng hợp cấu trúc mã nguồn, kiến trúc thiết kế, cấu trúc dữ liệu và **kết quả audit đã xác thực** trên toàn bộ repository (`main`).

---

## 1. Cấu trúc thư mục tổng thể

- `README.md` & `Makefile`: Tài liệu tổng quan và các target tự động hóa (`setup`, `infra`, `deploy`, `verify`, `lint`, `test`, `ui`, `teardown`).
- `infra/`:
  - `infra/cli.py`: Python Platform CLI (`Typer` + `Rich`) quản lý vòng đời 3 cụm `k3d`, giả lập WAN (`tc netem`), đồng bộ CoreDNS, sinh/đồng bộ chứng chỉ mTLS qua `cert-manager`, pre-pull/import container images và đăng ký spoke vào Argo CD.
  - `infra/scripts/register_argocd_spokes.py`: Đăng ký `aws-k3d` và `azure-k3d` vào Argo CD trên Hub.
- `deploy/`: Toàn bộ Kubernetes manifests theo nguyên tắc **SRP** (mỗi file 1 tài nguyên, tiền tố `00-`, `01-`, ...) và **Kustomize**:
  - `deploy/platform/`: OTel Collector (`edge/` & `gateway/`), Prometheus + Thanos (`metrics-thanos/`), Loki (`logs-loki/`), Tempo (`traces-tempo/`), MinIO (`storage-minio/`), Grafana + 10 dashboards (`visualization-grafana/`), Pyrra SLO (`slo-pyrra/`), Alertmanager (`alertmanager/`), Robusta Runner (`smart-alerting-robusta/`), `cert-manager/`, `sealed-secrets/`.
  - `deploy/clusters/`: Overlay riêng cho `hub/`, `aws/`, `azure/`.
  - `deploy/argocd/`: `ApplicationSet` cho Hub (`applicationset-hub.yaml`) và Spokes (`applicationset-spokes.yaml`).
  - `deploy/policies/`: Active `NetworkPolicy` (`teastore`, `monitoring`, `storage`) và static Kyverno `ClusterPolicy`.
- `workloads/teastore/`: Ứng dụng benchmark microservices Java **Descartes TeaStore v1.4.1**, tách compute sang `aws-spoke` và data/MySQL sang `azure-spoke`.
- `ai-engine/`: Module AI Engine V3 thu thập telemetry, tiền xử lý, huấn luyện và suy luận/RCA thời gian thực.
- `tests/`: Bộ kiểm thử tĩnh/hệ thống (`tests/scripts/`), sinh tải (`tests/locust/`), và chaos engineering (`tests/chaos/` với `run_live.py`, `run_service_faults.py`, `FaultAgent.java`).
- `docs/`: Tài liệu kiến trúc (`architecture.md`), 12 bản ADR (`docs/adr/`), 7 SRE runbooks (`docs/runbooks/`), và báo cáo phân tích này (`CODEBASE_ANALYSIS.md`).

---

## 2. Kiến trúc thiết kế hệ thống

### 2.1. Mô hình Hub-Spoke & Giả lập WAN
Trong `infra/cli.py`, hệ thống dựng 3 cụm `k3d` (`rancher/k3s:v1.31.2-k3s1`, tắt `traefik` và `metrics-server`) trên Docker bridge `mc-monitoring-net` (`172.28.0.0/16`):

1. **`aws-k3d` (Compute Spoke)**: Chạy 5 services TeaStore (`webui`, `auth`, `image`, `recommender`, `registry`) gắn `opentelemetry-javaagent:2.10.0` + `OTel Edge Collector`.
2. **`azure-k3d` (Data Spoke)**: Chạy `teastore-persistence` + `teastore-db` (`descartesresearch/teastore-db:1.4.1`) + `OTel Edge Collector` (kèm MySQL receiver patch).
3. **`hub-k3d` (Central Observability Hub)**: Nhận telemetry qua mạng WAN giả lập bằng `tc netem` (mặc định RTT `10ms ± 2ms`, loss `0.1%`).

### 2.2. Luồng Telemetry (OpenTelemetry Pipeline)
- **Spoke Edge (`deploy/platform/otel-collector/edge/02-configmap.yaml`)**:
  - Thu nhận qua `otlp` (gRPC `:4317`, HTTP `:4318`), `hostmetrics`, `filelog`, `kubeletstats`, `prometheus/internal`.
  - Lọc nhiễu tại biên (`filter/drop_noise`, `filter/logs`), `tail_sampling` (giữ 100% lỗi, latency > 1500ms, 20% normal), gắn metadata K8s/cloud (`k8sattributes`, `transform/cluster_id`).
  - Gửi về Hub qua `otlp/hub` dùng **Native mTLS 1.3** (`cert-manager v1.16.2`, per-spoke client cert).
- **Hub Gateway (`deploy/platform/otel-collector/gateway/03-configmap.yaml`)**:
  - Chuẩn hóa thuộc tính (`transform/normalize_cloud`), chạy `servicegraph` connector và `tail_sampling` (giữ 100% error, latency > 1500ms, 5% routine).
  - Lưu trữ phân tầng trên **MinIO S3**:
    - **Metrics**: Prometheus `:8889` scrape từ OTel Gateway, chạy cùng **Thanos Sidecar + Query + Store + Compact**.
    - **Logs**: Grafana Loki (`2.9.4`).
    - **Traces**: Grafana Tempo (`2.4.0`).
- **SLO, Visualization & Alerting**:
  - **Grafana (`11.5.0`)**: 10 dashboards chuẩn hóa.
  - **Pyrra (`v0.7.3`)** $\to$ **Alertmanager (`v0.27.0`)** $\to$ **Robusta Runner (`0.53.0`)** $\to$ **Telegram**.

### 2.3. Kiến trúc AI Engine V3 (`ai-engine/`)
1. **Dynamic Entity Discovery (`data/collector.py`)**: Dùng PromQL vectorized `by (k8s_cluster_name, cloud_provider, service_name)` tự động phát hiện thực thể, bất biến khi scale pod (`1 -> N`).
2. **Zero-Leakage Preprocessing (`data/preprocess.py`)**: Chia train/val theo trục thời gian từng thực thể trước khi tính baseline (`fit_scope = "train_only"`), điền thiếu nhân quả (`impute_causally`), tạo sliding window không chồng lấn.
3. **Ensemble Deep Autoencoders (`models/`, `training/train.py`)**:
   - `GRUAutoencoder`: Encoder 2-layer GRU (`input_dim=8`, `hidden_dim=64`, `dropout=0.1`) $\to$ bottleneck `latent_dim=16` $\to$ repeat theo `seq_len` $\to$ Decoder 2-layer GRU.
   - `TCNAutoencoder`: Encoder 3 `TemporalBlock` (Causal `Conv1d` + `Chomp1d`, `GELU`, residual, dilation `[1, 2, 4]`) $\to$ `Conv1d(64 -> 16, k=1)` $\to$ Decoder dilation `[4, 2, 1]`.
   - `IsolationForest`: Huấn luyện trong `train.py` trên vector phẳng 96 chiều (`12 * 8`), nhưng vòng lặp online trong `detector.py` hiện dùng trung bình `0.5 * (GRU + TCN)`.
4. **Unified Scoring & Dual Sliding Window (`models/scoring.py`)**:
   - `compute_directional_errors`: Trọng số bất đối xứng theo hướng tốt/xấu của metric và suy giảm theo thời gian (`RECENCY_DECAY_RATE = 0.45`).
   - `DualSlidingWindowScorer`: Kết hợp `short_window=3`, `long_window=18`, `min_consecutive_breaches=2` để phân biệt `TRANSIENT_SPIKE_SUPPRESSED` và `ALERT`, tính `likelihood_pct` bằng logistic anchored tại ngưỡng (`0.35`).
5. **Streaming Recovery & Cross-Cloud Trace RCA (`inference/streaming.py`, `inference/detector.py`)**:
   - `HistogramDeltas`: Tính P95 từ delta counter giữa 2 lần export liên tiếp.
   - `LatencyRecovery`: Xóa lịch sử latency/CPU khi có request mới + probe xác nhận hồi phục; giữ nguyên lịch sử RAM/GC.
   - `TempoTraceAnalyzer` + `TraceEvidence`: Bóc tách `T_WAN`, `T_self`, `T_DB` từ Tempo spans (TTL `90s`) và tổng hợp trong `synthesize_multicloud_rca`.

---

## 3. Cấu trúc dữ liệu

### 3.1. Định danh thực thể & 8 Universal Entity Features
Khóa định danh: `(cloud_provider, service_name)` (chuỗi `"<cloud>:<service>"`). Vector đặc trưng $\mathbf{x}_e^{(t)} \in \mathbb{R}^8$:

| #   | Tên feature          | Ý nghĩa                                              | `physical_scale_floor` |
| --- | -------------------- | ---------------------------------------------------- | ---------------------- |
| 0   | `qps`                | Tần suất request HTTP server (`req/s`)               | `5.0`                  |
| 1   | `server_latency_p95` | Độ trễ P95 phía server (`s`)                         | `0.035`                |
| 2   | `client_latency_p95` | Độ trễ P95 phía client (`s`)                         | `0.035`                |
| 3   | `error_rate_5xx`     | Tỷ lệ lỗi HTTP 5xx (`req/s`)                         | `0.10`                 |
| 4   | `max_pod_cpu_pct`    | % CPU cao nhất trong các pod active của service      | `12.0`                 |
| 5   | `max_pod_ram_pct`    | % Heap RAM cao nhất trong các pod active của service | `12.0`                 |
| 6   | `ram_floor_2m_pct`   | Đáy (min) của `max_pod_ram_pct` gần đây              | `10.0`                 |
| 7   | `gc_pause_rate`      | Tốc độ thời gian dừng JVM GC (`s/s`)                 | `0.015`                |

### 3.2. Chuẩn hóa & Tensor đầu vào
- Chuẩn hóa Z-score robust theo từng thực thể:
  $$z_{e,k}^{(t)} = \text{clip}\left(\frac{x_{e,k}^{(t)} - \text{median}_{e,k}}{\max(\text{IQR}_{e,k},\; \text{floor}_k)},\; -10.0,\; +10.0\right)$$
- Thực thể mới chưa có baseline được `EntityCalibrator` thu thập `30` mẫu online để tự hiệu chỉnh.
- Tensor đầu vào Autoencoder: `(Batch, window_size=12, num_features=8)` kiểu `float32`.

### 3.3. Metadata & Runtime Data trong `detector.py`
- `ai-engine/models/saved/entity_baselines.json`: Tham số `median`, `iqr`, `floor`, `scale`, `p95`, `p99` cho từng entity và `__default__`.
- `ai-engine/models/saved/threshold_config.json`: Phân phối sai số validation, `recommended_threshold_p99: 0.35`, tham số `dual_sliding_window`, `likelihood_calibration`, `feature_rca_baselines`.
- Runtime `detector.py`: `entity_buffers` (FIFO 12 bước), `entity_results`, `trace_summary`, `stats_summary["records"]`, và Prometheus exporter tại `:9108/metrics` (`ai_anomaly_likelihood_percent`, `ai_reconstruction_error`, `ai_rca_component_latency_ms`, `ai_detector_verdict`, `ai_probe_latency_ms`).

---

## 4. Kết quả Audit & Xác thực Mã nguồn (Cập nhật 2026-11-25)

### 4.1. Bằng chứng kiểm chứng trực tiếp (Live Verification)
- `pytest tests/scripts/ -q`: **142/142 passed** trong `22.67s` (exit code `0`).
- `python tests/scripts/validate_otel_rules.py`: Exit code `0` (*lưu ý: Rule #2 hiện bị bỏ qua do lệch tên pipeline, xem mục 4.2*).
- `kubectl kustomize` trên cả 5 targets (`deploy/clusters/hub`, `deploy/clusters/aws`, `deploy/clusters/azure`, `deploy/policies`, `deploy/argocd`): **Tất cả exit code `0`**.

### 4.2. Lỗi logic & sai lệch cấu hình đã xác thực

#### A. Các lỗi từ bản audit trước (Đã xác thực 100% CONFIRMED)
1. **Lệch entity giữa `entity_baselines.json` (4 cụm cũ) và cấu hình 3 cụm hiện tại — CONFIRMED**
   - `ai-engine/models/saved/entity_baselines.json:218-220,362-364` và `ai-engine/data/processed/preprocess_summary.json:13,15` chứa `azure:teastore-auth` và `gcp:teastore-recommender`, trong khi `deploy/clusters/aws/` đặt 2 service này ở `aws-k3d` (`cloud_provider="aws"`).
   - `ai-engine/configs/model_config.yaml` không ghi đè `inference.required_entities`, nên `detector.py:1131-1136,1313-1314` luôn có `missing_entities` khác rỗng và trả về `verdict = "UNKNOWN"`.
2. **Lệch phiên bản `k3s` trong `infra/cli.py` — CONFIRMED**
   - `infra/cli.py:34` dùng `K3S_IMAGE_DEFAULT = "rancher/k3s:v1.31.2-k3s1"`, nhưng `pull_images_cmd` (`infra/cli.py:465`) lại kéo `"rancher/k3s:v1.31.4-k3s1"`.
3. **Validator OTel kiểm tra nhầm tên pipeline (`tests/scripts/validate_otel_rules.py:90-93`) — CONFIRMED**
   - Kiểm tra `if "traces/servicegraph" in service_pipelines:`, trong khi `deploy/platform/otel-collector/gateway/03-configmap.yaml:185-205` đặt tên các pipeline là `traces`, `traces/storage`, `metrics`, `metrics/servicegraph`, `logs`. Rule #2 thực tế chưa bao giờ chạy.
4. **Query thừa/lệch label trong `CLOUD_VECTOR_QUERIES` (`ai-engine/data/collector.py:114-117,269-289` & `detector.py:272-284,1156`) — CONFIRMED**
   - `wan_latency_p95` không có label `cloud_provider` nên luôn bị bỏ qua khi lọc theo `cloud_provider`; `wan_network_drops` được query nhưng không sử dụng ở vòng lặp inference.

#### B. Các lỗi logic & vận hành MỚI phát hiện khi audit sâu
5. **Pyrra SLO Rules không bao giờ được Prometheus nạp & đánh giá**
   - `deploy/platform/slo-pyrra/02-deployment.yaml:61-64` chạy `pyrra kubernetes --config-maps-only` (ghi rules vào `ConfigMap`), nhưng `deploy/platform/metrics-thanos/03-statefulset-prometheus.yaml:46-50,116-118` chỉ mount static `prometheus-rules` và không có sidecar/reloader tự động nạp các ConfigMap do Pyrra sinh ra.
6. **Azure MySQL Receiver nguy cơ lỗi xác thực (`root` + `optional: true` secret)**
   - `deploy/clusters/azure/patches/01-configmap-mysql-receiver.yaml:9-12` kết nối `teastore-db` bằng `username: root` và `${env:MYSQL_ROOT_PASSWORD}` từ `teastore-mysql-secret` (`patch-cluster-identity.yaml:23-28`, `optional: true`). Tuy nhiên `teastore-mysql-secret` không tồn tại trong `deploy/clusters/azure/` hay `workloads/teastore/azure-spoke/`, nên biến môi trường bị rỗng.
7. **`tests/chaos/run_service_faults.py:33` trỏ sai loại tài nguyên K8s (`deploy/teastore-db`)**
   - `workloads/teastore/azure-spoke/01-mysql-statefulset.yaml:2-4` là `kind: StatefulSet`, nên lệnh `kubectl exec deploy/teastore-db` sẽ lỗi `deployments.apps "teastore-db" not found` (phải là `statefulset/teastore-db`).
8. **`Makefile:65-67` (`sync-secrets`) thiếu `--context $(HUB_CTX)`**
   - Nếu kubeconfig hiện tại đang trỏ vào một Spoke cluster, `make sync-secrets` sẽ apply nhầm manifest Hub sang Spoke.
9. **Dead parameters & nối chuỗi IP trong `infra/cli.py`**
   - `certs_cmd` (`infra/cli.py:283-284,296-303`) có 2 tham số thừa `pki_dir`, `force` không dùng và bỏ qua returncode của `kubectl wait`.
   - `sync_hosts_cmd` (`infra/cli.py:421`) dùng template Go `{{range ...}}{{$conf.IPAddress}}{{end}}` không có dấu phân cách, sẽ nối dính IP nếu container gắn nhiều network.

### 4.3. Điều kiện môi trường & Artifact
- **Weights & dữ liệu nặng trong Git:** `gru_autoencoder.pt`, `tcn_autoencoder.pt`, `isolation_forest.joblib`, `multicloud_entity_baseline.csv`, `train_windows.npy`, `val_windows.npy` được gitignore; cần chạy `collector.py` $\to$ `preprocess.py` $\to$ `train.py` để tái tạo.
- **Môi trường Python & CLI:** Đã xác thực `pytest tests/scripts/` chạy pass **142/142** trên môi trường hiện tại; `Makefile` dùng `SHELL := /bin/bash` nên trên Windows cần chạy qua Git Bash hoặc WSL2.
- **Kustomize `deploy/argocd`:** Tham chiếu URL từ xa (`core-install.yaml`); build pass khi có Internet, nhưng sẽ lỗi nếu chạy offline/air-gapped.

### 4.4. Sai lệch tài liệu & giới hạn đã ghi nhận
- `docs/architecture.md:14,21,25,45,61,69-73`: Vẫn ghi Thanos `Receive, Query, Ruler`, `8 Dashboards`, và `MySQL 8.0` (thực tế: `Prometheus + Thanos Sidecar/Query/Store/Compact`, **10** dashboards, `teastore-db:1.4.1`).
- `docs/runbooks.md:87,112,115,221,234,245` & `docs/github-setup.md:84-89`: Chứa nhiều lệnh/đường dẫn cũ không còn tồn tại (`daemonset/otel-collector`, `revert_chaos.py`, `wan --delay`, `statefulset/thanos-receive`, `security/pki/`, `make update-certs`).
- `ai-engine/models/gru_autoencoder.py:18`: Docstring cũ ghi `Features=14` (thực tế `8`).
- `IsolationForest`: Được train trong `train.py` nhưng chưa dùng khi suy luận online trong `detector.py`.
- Giới hạn chaos benchmark đã ghi nhận trong `tests/chaos/IMPROVEMENTS-2026-10-31.md`.

---

## 5. Kết quả Security Audit Hiện Tại (0 Critical, 4 High, 7 Medium, 4 Low)

### High
1. **Unsafe Deserialization Fallback (`ai-engine/inference/detector.py:1007-1013,1041`):** `_safe_torch_load()` fallback về `weights_only=False` khi gặp lỗi, và vẫn gọi `joblib.load(iso_path)` dù `iso_forest` không được dùng (nguy cơ RCE qua pickle).
2. **Kubelet TLS Verification Disabled (`deploy/platform/otel-collector/edge/02-configmap.yaml:58`):** `kubeletstats` đặt `insecure_skip_verify: true` khi gửi kèm ServiceAccount Bearer token tới `:10250`.
3. **NetworkPolicy chặn AI Engine (`:9108`) & thiếu peer selectors (`deploy/policies/11-*`, `12-*`):**
   - `12-monitoring-storage-networkpolicy.yaml` thiếu port `9108` trong `egress`, làm Prometheus (`01-configmap-prometheus.yaml:60-64`) bị chặn khi scrape `host.k3d.internal:9108`.
   - Nhiều rule egress/ingress trong `11-*` và `12-*` chưa giới hạn `from:` / `to:` peer selector.
4. **Remote Manifest chưa ghim SHA256 (`deploy/argocd/kustomization.yaml:8`):** Pull trực tiếp `core-install.yaml` từ GitHub URL theo tag `v2.12.3` mà không có hash/vendor nội bộ.

### Medium
1. **Plaintext Placeholder Secrets (`deploy/clusters/hub/kustomization.yaml:26-70`, `smart-alerting-robusta/01-secret.yaml:7-10`):** Dùng `CHANGE_ME_*` thay vì `SealedSecret` CRD.
2. **Giao tiếp nội bộ Hub không mã hóa & tắt Auth:** OTel Gateway $\to$ Loki/Tempo, Thanos/Loki/Tempo $\to$ MinIO S3 (`insecure: true`), Loki `auth_enabled: false`, MinIO `MINIO_PROMETHEUS_AUTH_TYPE: "public"`.
3. **Kyverno `03-disallow-root-user.yaml` ở chế độ `Audit` & thiếu `runAsNonRoot` / `readOnlyRootFilesystem`:** 5 TeaStore deployments (`registry`, `auth`, `image`, `recommender`, `persistence`) và phần lớn Hub workloads chưa set `runAsNonRoot: true` / `readOnlyRootFilesystem: true`; `06-policy-exception-mysql.yaml` dư thừa.
4. **RBAC dư quyền (`otel-collector-hub` `gateway/02-rbac.yaml:6-26` & `register_argocd_spokes.py:79-213`):** `otel-collector-hub` có quyền `nodes/proxy,stats,spec` dù không scrape node; `argocd-manager` dùng static token secret và quyền cluster-wide `secrets` / `kyverno.io`.
5. **LoadBalancer lộ metrics không xác thực (`gateway/05-service.yaml:9-24`):** Service `LoadBalancer` của `otel-collector-hub` mở cả `:8888`, `:8889` ra ngoài cùng với `:4317`, `:4318`.
6. **Runtime `apk add` & shell f-string (`infra/cli.py:251-271,567-572`):** Container `--cap-add=NET_ADMIN` cài `iproute2` không ghim version lúc runtime.
7. **MySQL Receiver dùng `root` (`deploy/clusters/azure/patches/01-configmap-mysql-receiver.yaml:10-12`):** Nên dùng user monitoring read-only riêng (`PROCESS, REPLICATION CLIENT, SELECT`).

### Low / Info
- Platform images & `autoinstrumentation-java:2.10.0` mới ghim theo tag, chưa ghim `@sha256:` digest.
- `smart-alerting-robusta/03-runner-deployment.yaml:44-49` bật `LOG_LEVEL: "DEBUG"` và `TRACE_INCOMING_*` mặc định.
- Điểm tốt đã đạt: mTLS 1.3 + per-spoke client certs chuẩn chỉ; Kyverno Enforce chặn `:latest`, missing limits/probes, privilege escalation; `detector.py` bind `127.0.0.1:9108`, escape HTML Telegram và ẩn token khỏi log.

---

## 6. Đề xuất thứ tự ưu tiên khắc phục (Next Action)

1. **Ưu tiên 1 (Đã khắc phục `[RESOLVED]` — commits `2738532`, `8e0b18c`):**
   - `[RESOLVED]` Mở port `:9108` trong `12-monitoring-storage-networkpolicy.yaml` để Prometheus scrape được AI Engine.
   - `[RESOLVED]` Sửa `deploy/teastore-db` $\to$ `statefulset/teastore-db` trong `tests/chaos/run_service_faults.py:33`.
   - `[RESOLVED]` Sửa `validate_otel_rules.py:90` (`"traces"` thay vì `"traces/servicegraph"`), đồng bộ `rancher/k3s:v1.31.2-k3s1` trong `infra/cli.py:465`, và thêm `--context $(HUB_CTX)` cho `sync-secrets` trong `Makefile`.
   - `[RESOLVED]` Bỏ fallback `weights_only=False` và bỏ `joblib.load(iso_path)` thừa trong `detector.py`; cấu hình `ca_file` + `insecure_skip_verify: false` cho `kubeletstats`.
   - `[RESOLVED]` Vendor `deploy/argocd/01-core-install.yaml` (`v2.12.3`) nội bộ để build offline không phụ thuộc URL GitHub.
   - `[RESOLVED]` Gắn `pyrra-rules-sidecar` (`kiwigrid/k8s-sidecar:1.28.0`) cho Prometheus (`03-statefulset-prometheus.yaml`) để nạp rules Pyrra.
2. **Ưu tiên 2 (Đã khắc phục `[RESOLVED]` — Đồng bộ AI Engine & MySQL):**
   - `[RESOLVED]` Cấu hình `inference.required_entities` (6 active 3-cluster TeaStore entities) trong `ai-engine/configs/model_config.yaml`.
   - `[RESOLVED]` Bỏ `wan_network_drops` chưa dùng và bổ sung `cloud_provider` vào `wan_latency_p95` trong `ai-engine/data/collector.py`; sửa docstring `Features=8` trong `gru_autoencoder.py`.
   - `[RESOLVED]` Provision `teastore-mysql-secret` đồng bộ qua `secretGenerator` trong `deploy/clusters/azure/kustomization.yaml`.
3. **Ưu tiên 3 (Đã khắc phục `[RESOLVED]` — Hardening & Docs):**
   - `[RESOLVED]` Tách `:8888`/`:8889` sang `ClusterIP` service riêng (`otel-collector-hub-metrics`), bỏ `nodes/proxy`, `nodes/stats`, `nodes/spec` thừa khỏi `otel-collector-hub` RBAC, thêm `.worktrees/` vào `.gitignore`, và dọn lệnh cũ trong `docs/architecture.md`, `docs/runbooks.md`, `docs/github-setup.md`.
4. **Ưu tiên 4 (Đã khắc phục `[RESOLVED]` — Remaining Hardening & CI Guards):**
   - `[RESOLVED]` Khắc phục `test_task17` CI guards, dọn dead parameters trong `infra/cli.py` (`certs_cmd`) và sửa nối chuỗi IP trong `sync_hosts_cmd`.
   - `[RESOLVED]` Bật `runAsNonRoot: true` cho các TeaStore deployments và nâng Kyverno `03-disallow-root-user.yaml` lên chế độ `Enforce`.
   - `[RESOLVED]` Chuyển Robusta (`03-runner-deployment.yaml`) sang `LOG_LEVEL: "INFO"`, bổ sung NetworkPolicy peer selectors (`11-*`, `12-*`), và đặt `optional: false` cho Azure `teastore-mysql-secret` (`patch-cluster-identity.yaml`).
