# Kế Hoạch & Kịch Bản Kiểm Thử Kênh Cảnh Báo Telegram (Alertmanager, Robusta & AI Anomaly Engine)

> **Tài liệu:** `docs/progress/04_Telegram_test.md`  
> **Phiên bản:** `v1.0.0` (Cập nhật ngày 16/11/2026)  
> **Trạng thái:** Sẵn sàng kiểm thử thực tế (Ready for Execution)  
> **Mục tiêu:** Cung cấp hướng dẫn toàn diện, trạng thái hiện tại, điều kiện kích hoạt và các bước thực thi kiểm thử có thể tái lập (reproducible) để xác minh chuỗi cảnh báo từ Prometheus, Alertmanager, Robusta Runner và AI Engine V3 về Telegram.

---

## 1. Phân Tích Hiện Trạng & Khắc Phục Nguyên Nhân "Chưa Thấy Thông Báo" Sáng Nay

Trước khi tiến hành kiểm thử, hệ thống đã được rà soát và tìm ra 3 nguyên nhân cốt lõi khiến chưa có thông báo tự động nào được đẩy về Telegram trong buổi sáng:

| STT | Vấn đề phát hiện | Nguyên nhân kỹ thuật | Biện pháp đã xử lý triệt để | Trạng thái hiện tại |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **Prometheus lỗi kết nối Notifier (404 Not Found)** | Cấu hình Prometheus cũ trỏ trực tiếp sang `robusta-runner:5000`. Prometheus đẩy alert theo giao thức server Alertmanager (`POST /api/v2/alerts`), trong khi Robusta Runner chỉ tiếp nhận webhook Alertmanager tại `/api/alerts`. | Đã triển khai chính thức thành phần **`Alertmanager v0.27.0`** (chuẩn SRP: `k8s/base/alertmanager/`), làm cầu nối nhận `/api/v2/alerts` từ Prometheus và bắn Webhook `/api/alerts` sang Robusta. | **ĐÃ HOÀN TẤT** (Alertmanager 1/1 Running) |
| **2** | **Robusta Playbook dừng xử lý do thiếu Pod** | Cấu hình playbook cũ dùng `pod_events_enricher` cho mọi alert. Với các alert không gắn nhãn Pod (như mất kết nối WAN hay nhịp tim cụm), Robusta báo lỗi `cannot run pod_events_enricher on alert with no pod object` và hủy gửi tin nhắn. | Đã cấu hình `default_enricher` (với `alert_annotations_enrichment: true`) làm hành động chuẩn cho mọi alert Prometheus, hiển thị đầy đủ bảng nhãn và mô tả. | **ĐÃ HOÀN TẤT** (Robusta 1/1 Running) |
| **3** | **Động cơ AI Detector chưa chạy daemon** | Module `ai-engine/inference/detector.py` là tiến trình chạy độc lập, chưa được khởi động trên cổng `:9108` của trạm làm việc, do đó `ai_anomaly_likelihood_percent` chưa xuất số liệu và sink Telegram nội bộ chưa kích hoạt. | Đã chuẩn bị môi trường thực thi và kịch bản khởi chạy AI Detector V3 với cờ xuất metric `--metrics-port 9108` và rate-limit 30s. | **SẴN SÀNG KHỞI CHẠY** |

---

## 2. Bảng Danh Mục Trạng Thái & Điều Kiện Kích Hoạt Cảnh Báo

Hệ thống cảnh báo đa đám mây gồm 2 kênh chính:
1. **Kênh Hạ Tầng & Quy Tắc Số Liệu (Prometheus $\rightarrow$ Alertmanager $\rightarrow$ Robusta $\rightarrow$ Telegram)**
2. **Kênh Trí Tuệ Nhân Tạo & Phân Rã Vết (AI Anomaly Detector V3 $\rightarrow$ Telegram Sink & Prometheus :9108)**

### 2.1. Danh mục 6 Alert Rules của Prometheus & Alertmanager

| Tên Quy Tắc (Alert Name) | Mức Độ (Severity) | Biểu Thức PromQL Kiểm Tra | Điều Kiện & Thời Gian Chờ (`for`) | Mục Đích & Ý Nghĩa Kỹ Thuật | Trạng Thái Hiện Tại |
| :--- | :---: | :--- | :---: | :--- | :---: |
| **`SpokeClusterHeartbeatAbsent`** | `critical` | `absent(up{k8s_cluster_name="aws-k3d"} == 1) or absent(up{k8s_cluster_name="azure-k3d"} == 1)` | Không nhận được nhịp tim từ Spoke trong **2 phút** (`120s`). | Cảnh báo đứt cáp quang WAN, rớt mạng Docker Bridge `mc-monitoring-net`, hoặc container OTel Collector tại Spoke bị sập hoàn toàn. | **FIRING** (Sẵn sàng gửi) |
| **`MicroserviceHighErrorRate`** | `high` | `(sum by (server) (rate(traces_service_graph_request_failed_total[2m])) / (sum by (server) (rate(traces_service_graph_request_total[2m])) + 0.0001)) * 100 > 5` | Tỷ lệ lỗi giao dịch vi dịch vụ vượt **5%** liên tục trong **2 phút** (`120s`). | Bắt lỗi mã nguồn microservice (HTTP 500, Exception, DB Connection Refused) từ đồ thị dịch vụ OTel. | **INACTIVE** (0% lỗi) |
| **`CrossCloudWANLatencyDegraded`** | `high` | `histogram_quantile(0.99, sum by (le, server) (rate(traces_service_graph_request_server_seconds_bucket[2m]))) * 1000 > 1500` | Độ trễ P99 xuyên đám mây vượt **1500ms** liên tục trong **2 phút** (`120s`). | Bắt tình trạng nghẽn mạng WAN do suy hao `tc netem` hoặc truy vấn JDBC cơ sở dữ liệu bị khóa bảng. | **FIRING / PENDING** (WAN có tiêm trễ) |
| **`OTelCollectorMemoryHigh`** | `warning` | `sum by (pod) (container_memory_working_set_bytes{pod=~"otel-collector.*"}) > 4e+08` | Bộ nhớ RAM Working Set của collector vượt **400MB** liên tục trong **2 phút** (`120s`). | Cảnh báo sớm nguy cơ tràn bộ đệm `memory_limiter` hoặc bị Linux OOMKilled khi có bão viễn trắc. | **INACTIVE** (Đang dùng ~60MB) |
| **`SpokePodCrashLooping`** | `critical` | `(rate(k8s_container_restarts_total[5m]) > 0) or (changes(process_uptime_seconds[5m]) > 2) or (increase(kube_pod_container_status_restarts_total[5m]) > 1)` | Pod trên cụm Spoke bị restart $> 1$ lần trong **1 phút** (`60s`). | Bắt kịp thời các sự cố Pod chết đi sống lại (như sự cố probe Recommender/Image trước đó). | **INACTIVE** (0 restarts) |
| **`AIOpsAnomalyDetected`** | `critical` | `ai_anomaly_likelihood_percent > 80` | Xác suất bất thường từ mô hình học sâu vượt **80%** liên tục trong **30 giây** (`30s`). | Cảnh báo bất thường tổng hợp đa chiều (CPU, RAM, trễ, lỗi) do động cơ AI V3 xuất qua cổng `:9108`. | **INACTIVE** (Chờ khởi động AI) |

### 2.2. Kênh Động Cơ Trí Tuệ Nhân Tạo AI Anomaly Engine V3

| Tín Hiệu / Thuộc Tính | Ngưỡng Kích Hoạt | Cơ Chế Phân Rã Vết (RCA) | Kênh Tiếp Nhận & Hành Động |
| :--- | :--- | :--- | :--- |
| **`verdict == ALERT`** | Điểm lỗi tái tạo tức thời (Instant MSE) và cửa sổ ngắn (Short Window MSE) vượt ngưỡng động **`> 0.3500`**, đồng thời xác suất bất thường **`likelihood_pct > 80%`** duy trì liên tục qua 3 chu kỳ đo (18 giây). | Tự động phân rã dấu vết phân tán (Distributed Trace Spans) từ Tempo: <br>• $T_{\text{WAN}}$: Độ trễ trượt mạng diện rộng xuyên mây.<br>• $T_{\text{self}}$: Thời gian tự xử lý nội tại của Pod.<br>• $T_{\text{DB}}$: Thời gian thực thi câu lệnh SQL/JDBC. | **1. Gửi Telegram trực tiếp:** Bắn tin nhắn Markdown định dạng giàu thông tin, đính kèm bảng định lượng RCA và khuyến nghị xử lý.<br>**2. Xuất Prometheus Metric:** Xuất `ai_anomaly_likelihood_percent` lên `:9108` để kích hoạt rule Alertmanager song song. |

---

## 3. Kịch Bản Kiểm Thử Chi Tiết Từng Bước (Test Execution Runbook)

Bạn có thể thực hiện kiểm thử lần lượt theo 5 kịch bản dưới đây trên môi trường WSL Linux. Mỗi kịch bản đều có lệnh kích hoạt, kết quả hiển thị trên Telegram và lệnh dọn dẹp/khôi phục hệ thống.

---

### Kịch Bản 0: Kiểm Tra Nhanh Đường Truyền Trực Tiếp Telegram (Smoke Test)
*Mục đích: Xác thực ngay lập tức bot token và chat_id đã thông suốt tới tài khoản Telegram của bạn.*

1. **Thực thi lệnh kiểm tra trực tiếp từ Robusta Runner Pod:**
   ```bash
   wsl -d Ubuntu -e kubectl --context=k3d-hub-k3d -n monitoring exec deployment/robusta-runner -- python3 -c "
   from robusta.core.sinks.telegram.telegram_client import TelegramClient
   import os
   token = os.environ.get('TELEGRAM_BOT_TOKEN')
   chat_id = os.environ.get('TELEGRAM_CHAT_ID')
   client = TelegramClient(chat_id=chat_id, thread_id=None, bot_token=token)
   client.send_message('🔔 *[MultiCloud Observability]* Smoke Test kiểm tra kết nối Telegram thành công 100%!')
   print('Đã gửi tin nhắn thành công!')
   "
   ```
2. **Kết quả mong đợi:**
   - Trên Telegram của bạn nhận được tin nhắn:  
     `🔔 [MultiCloud Observability] Smoke Test kiểm tra kết nối Telegram thành công 100%!`

---

### Kịch Bản 1: Giả Lập Pod Khởi Động Lại Liên Tục (Test Rule `SpokePodCrashLooping`)
*Mục đích: Kiểm tra khả năng bắt lỗi tự động khi có Pod microservice trên cụm Spoke bị crash hoặc cấu hình sai.*

1. **Kích hoạt sự cố (Tạo Pod lỗi crash liên tục trên cụm `aws-k3d`):**
   ```bash
   wsl -d Ubuntu -e kubectl --context=k3d-aws-k3d -n teastore run crash-test-pod --image=busybox:1.36 --restart=Always -- /bin/sh -c "sleep 2; exit 1"
   ```
2. **Quan sát quá trình đánh giá:**
   - Pod `crash-test-pod` sẽ bị restart nhiều lần (`CrashLoopBackOff`).
   - Sau khoảng **60 giây**, biểu thức `rate(k8s_container_restarts_total[5m]) > 0` thỏa mãn.
   - Prometheus chuyển trạng thái rule sang **FIRING** $\rightarrow$ gửi sang Alertmanager $\rightarrow$ Robusta Runner.
3. **Kết quả mong đợi trên Telegram:**
   - Nhận thông báo cảnh báo từ Robusta với tiêu đề:
     `🚨 FIRING: SpokePodCrashLooping - Cụm Spoke: Phát hiện Pod khởi động lại liên tục (CrashLooping)`
   - Kèm bảng nhãn chi tiết: `k8s_cluster_name="aws-k3d"`, `namespace="teastore"`, `pod="crash-test-pod"`.
4. **Khôi phục & Dọn dẹp:**
   ```bash
   wsl -d Ubuntu -e kubectl --context=k3d-aws-k3d -n teastore delete pod crash-test-pod
   ```

---

### Kịch Bản 2: Giả Lập Đứt Gãy Mạng WAN / Mất Collector (Test Rule `SpokeClusterHeartbeatAbsent`)
*Mục đích: Kiểm tra phát hiện mất hoàn toàn số liệu viễn trắc từ một đám mây thành viên.*

1. **Kích hoạt sự cố (Tạm dừng Spoke Collector trên `aws-k3d`):**
   ```bash
   wsl -d Ubuntu -e kubectl --context=k3d-aws-k3d -n monitoring scale deployment otel-collector-spoke --replicas=0
   ```
2. **Quan sát quá trình đánh giá:**
   - Số liệu nhịp tim của cụm `aws-k3d` bị ngắt quãng.
   - Sau **2 phút**, biểu thức `absent(up{k8s_cluster_name="aws-k3d"} == 1)` chuyển sang kích hoạt.
   - Rule `SpokeClusterHeartbeatAbsent` kích hoạt mức độ **CRITICAL**.
3. **Kết quả mong đợi trên Telegram:**
   - Nhận thông báo cảnh báo khẩn cấp:
     `🚨 FIRING: SpokeClusterHeartbeatAbsent`
     `Mô tả: Không nhận được bất kỳ số liệu telemetry nào từ cụm Spoke (AWS hoặc Azure) về Central Hub trong hơn 2 phút.`
4. **Khôi phục hệ thống:**
   ```bash
   wsl -d Ubuntu -e kubectl --context=k3d-aws-k3d -n monitoring scale deployment otel-collector-spoke --replicas=1
   ```
   - Sau khi collector chạy lại khoảng 1 phút, Telegram sẽ nhận được thông báo giải quyết: `[RESOLVED] SpokeClusterHeartbeatAbsent`.

---

### Kịch Bản 3: Giả Lập Nghẽn Mạng Xuyên Mây (Test Rule `CrossCloudWANLatencyDegraded`)
*Mục đích: Kiểm tra phát hiện suy giảm chất lượng dịch vụ khi độ trễ mạng Internet vượt ngưỡng cam kết.*

1. **Kích hoạt sự cố (Tăng độ trễ mạng WAN lên 2 giây bằng `tc netem` trên node Azure):**
   ```bash
   wsl -d Ubuntu -e docker exec k3d-azure-k3d-server-0 tc qdisc change dev eth0 root netem delay 2000ms 50ms loss 5%
   ```
2. **Sinh lưu lượng gọi dịch vụ:**
   - Chạy lệnh curl liên tục vào trang TeaStore để phát sinh các giao dịch xuyên cụm từ WebUI (AWS) sang Persistence (Azure):
     ```bash
     wsl -d Ubuntu -e bash -c "for i in {1..20}; do curl -s 'http://localhost:8080/tools.descartes.teastore.webui/category?page=1&category=2' > /dev/null; sleep 1; done"
     ```
3. **Quan sát & Kết quả mong đợi trên Telegram:**
   - Độ trễ P99 đo được từ `traces_service_graph_request_server_seconds_bucket` sẽ vọt lên $> 2000\text{ms}$.
   - Sau **2 phút**, rule `CrossCloudWANLatencyDegraded` chuyển sang **FIRING**.
   - Telegram nhận thông báo:
     `🚨 FIRING: CrossCloudWANLatencyDegraded`
     `Mô tả: Dịch vụ teastore-webui / teastore-recommender có độ trễ P99 vượt 1500ms liên tục trong 2 phút.`
4. **Khôi phục đường truyền mạng WAN về tiêu chuẩn (10ms):**
   ```bash
   wsl -d Ubuntu -e docker exec k3d-azure-k3d-server-0 tc qdisc change dev eth0 root netem delay 10ms 2ms distribution normal loss 0.1%
   ```

---

### Kịch Bản 4: Khởi Chạy Động Cơ AI Detect V3 & Kiểm Thử Phân Rã Vết RCA
*Mục đích: Kiểm tra khả năng phát hiện bất thường tinh vi bằng mô hình Deep Learning (GRU + TCN) và tự động bóc tách nguyên nhân gốc rễ (WAN vs App vs DB).*

1. **Khởi chạy tiến trình AI Anomaly Detector daemon:**
   - Mở một cửa sổ terminal WSL mới và chạy lệnh:
     ```bash
     cd /mnt/d/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần\ 3/multicloud-monitoring
     python3 ai-engine/inference/detector.py --interval 6 --metrics-port 9108
     ```
   - Terminal sẽ hiển thị nhật ký khởi tạo:
     `[Detector] Initialized Universal GRU + TCN Autoencoders & Isolation Forest.`
     `[Detector] Serving Prometheus metrics on port 9108.`
     `[Detector] Monitoring 8 universal entity features across AWS, Azure, Hub.`
2. **Kích hoạt tình huống bất thường (Tiêm trễ mạng WAN 180ms vào Azure Spoke):**
   ```bash
   wsl -d Ubuntu -e docker exec k3d-azure-k3d-server-0 tc qdisc change dev eth0 root netem delay 180ms 15ms
   ```
   - Thực hiện một số giao dịch mua hàng hoặc duyệt sản phẩm trên WebUI: `http://localhost:8080/tools.descartes.teastore.webui/`
3. **Kết quả mong đợi trên Telegram (Định dạng RCA giàu ngữ cảnh):**
   - Động cơ AI phát hiện độ lệch Z-Score của `client_latency_p95` và `server_latency_p95`. Điểm MSE vọt lên $> 4.50$, Likelihood $> 90\%$.
   - Telegram sẽ nhận được thông điệp RCA đặc thù từ AI:
     ```text
     🚨 *[AI-OPS ALERT] Multi-Cloud Anomaly Detected*
     ━━━━━━━━━━━━━━━━━━━━━━━━━━
     📍 *Target Entity*: `azure:teastore-persistence`
     📊 *Likelihood*: `96.4%` (MSE: `5.1240`)
     ⚡ *Verdict*: `ALERT` (Sustained Anomaly)

     🔍 *Root Cause Evidence (RCA)*:
     • [CROSS_CLOUD_WAN_DELAY] aws->azure (T_WAN=194.2ms)
     • client_latency_p95 lệch chuẩn x85.4 so với baseline

     ⏱️ *Tempo Trace Decomposition*:
       • Cross-Cloud WAN Lag: `194.2ms`
       • Microservice Self-Exec: `14.1ms`
       • Database Query Time: `8.5ms`
     ━━━━━━━━━━━━━━━━━━━━━━━━━━
     💡 *Recommendation*: Inspect edge WAN shaping or database slow queries.
     ```
   - Đồng thời trên Prometheus, metric `ai_anomaly_likelihood_percent > 80` xuất hiện và kích hoạt rule cảnh báo `AIOpsAnomalyDetected`.
4. **Khôi phục hệ thống:**
   ```bash
   wsl -d Ubuntu -e docker exec k3d-azure-k3d-server-0 tc qdisc change dev eth0 root netem delay 10ms 2ms distribution normal loss 0.1%
   ```

---

## 4. Hướng Dẫn Xử Lý Nhanh Khi Cần Tắt Tiếng (Silence) & Điều Chỉnh Ngưỡng

- **Truy cập Alertmanager UI để quản lý cảnh báo:**  
  Bạn có thể mở port-forward để vào giao diện web của Alertmanager:
  ```bash
  wsl -d Ubuntu -e kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/alertmanager 9093:9093
  ```
  Truy cập `http://localhost:9093` để xem các nhóm cảnh báo đang gộp, hoặc tạo quy tắc tắt tiếng (Silence) trong thời gian bảo trì/chạy benchmark.
- **Điều chỉnh thời gian cooldown của Robusta:**  
  Trong file [k8s/base/smart-alerting-robusta/02-configmap-playbooks.yaml](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/smart-alerting-robusta/02-configmap-playbooks.yaml), biến `cooldown` mặc định được đặt để tránh hiện tượng bão thông báo (Alert Storm).
- **Xem nhật ký trực tiếp của Robusta Runner:**
  ```bash
  wsl -d Ubuntu -e kubectl --context=k3d-hub-k3d -n monitoring logs deployment/robusta-runner -f
  ```
