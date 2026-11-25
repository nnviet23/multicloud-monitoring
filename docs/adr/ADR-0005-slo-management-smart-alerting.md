# ADR-0005: SLO-as-Code Governance, Multi-Burn-Rate Alerting & Robusta Remediation

## Status
Implemented (Đã triển khai)

## Context
Trong môi trường microservices đa cụm phức tạp, các phương pháp cảnh báo ngưỡng tĩnh (static threshold alerting, ví dụ: CPU > 80% hoặc Error Rate > 5%) thường gây ra hai vấn đề nhức nhối:
1. **Nhiễu cảnh báo (Alert Fatigue):** Các xung tải đột ngột trong vài giây kích hoạt hàng loạt cảnh báo giả (false positives), khiến kỹ sư vận hành bỏ qua các thông báo quan trọng.
2. **Cảnh báo muộn đối với sự cố nghiêm trọng (Slow Burn Blindspots):** Một lỗi rò rỉ bộ nhớ hoặc tỷ lệ lỗi 1% diễn ra liên tục trong 12 giờ có thể không chạm ngưỡng tĩnh, nhưng sẽ làm cạn kiệt ngân sách lỗi (Error Budget) và vi phạm cam kết chất lượng dịch vụ (SLA).
3. **Thiếu ngữ cảnh chẩn đoán (Diagnostic Context Deficit):** Cảnh báo thông thường chỉ gửi thông điệp ngắn, buộc kỹ sư phải mở terminal chạy lệnh `kubectl describe pod` và `kubectl logs` thủ công để tìm hiểu nguyên nhân gốc rễ, kéo dài thời gian phát hiện và khôi phục sự cố (MTTD / MTTR).

## Decision
Chúng tôi quyết định áp dụng tiêu chuẩn **Google SRE SLO-as-Code** với **Pyrra** kết hợp động cơ cảnh báo thông minh và ứng phó sự cố tự động **Robusta**:

### 1. Quản trị SLO-as-Code Khai báo với Pyrra
- Triển khai **Pyrra** (`pyrra-kubernetes --config-maps-only` kết hợp `pyrra-api`) trên cụm `hub-k3d` để quản lý các mục tiêu mức dịch vụ từ `ConfigMap` mà không cần cài đặt CRD operator nặng:
  - Định nghĩa rõ ràng **Service Level Indicator (SLI)** dựa trên tỷ lệ yêu cầu thành công / tổng số yêu cầu (Availability) và độ trễ phản hồi (Latency).
  - Tự động sinh ra các quy tắc cảnh báo **Multi-Window Multi-Burn-Rate** chuẩn Google SRE Workbook:
    - **Cảnh báo khẩn cấp (Page/Critical):** Tiêu thụ ngân sách lỗi nhanh trong cửa sổ ngắn (ví dụ: cửa sổ 1 giờ tiêu hao > 5% ngân sách lỗi hoặc 6 giờ tiêu hao > 10% ngân sách lỗi).
    - **Cảnh báo mức thông báo (Ticket/Warning):** Rò rỉ ngân sách lỗi chậm trong cửa sổ dài (ví dụ: cửa sổ 3 ngày tiêu hao > 2% ngân sách lỗi).
- Đo lường trực tiếp từ các metrics chuẩn hóa xuất ra từ OpenTelemetry và Thanos Receive.

### 2. Cảnh báo Thông minh và Làm giàu Ngữ cảnh với Robusta
- Triển khai **Robusta Runner** trên `hub-k3d` để tiếp nhận webhook từ Alertmanager và làm giàu ngữ cảnh; việc triển khai **Robusta Forwarder** trên các cụm Spoke (`aws-k3d`, `azure-k3d`) được hoãn sang **Phase 5 (Real-Cloud)** để tối ưu ngân sách RAM cục bộ.
- Khi Prometheus Alertmanager kích hoạt một cảnh báo liên quan đến Pod hoặc Service, Robusta tự động kích hoạt Playbook thực thi các hành động sau:
  - Tự động thu thập 50 dòng log gần nhất của container phát sinh lỗi.
  - Tự động trích xuất các Kubernetes Events (như `OOMKilled`, `CrashLoopBackOff`, `FailedScheduling`).
  - Đóng gói toàn bộ thông tin chẩn đoán thành báo cáo định dạng giàu nội dung (Rich-text markdown + graph chart).

### 3. Tích hợp Kênh Thông báo Telegram với Đệm Hạ nhiệt 60 Giây (60s Cooldown Buffer)
- Định tuyến cảnh báo đến kênh Telegram quản trị thông qua Telegram Bot API Webhook.
- Cấu hình đệm hạ nhiệt **60s cooldown buffer** và cơ chế nhóm cảnh báo (alert grouping / deduplication) trong Alertmanager và Robusta:
  - Ngăn chặn tình trạng hàng chục tin nhắn cảnh báo bắn phá kênh chat cùng một lúc khi xảy ra sự cố sập tầng mạng liên cụm.
  - Nhóm các cảnh báo liên quan theo nhãn `k8s.cluster.name` và `service.name`.

### 4. Chuẩn Hóa Modular Alert Rules theo Domain từ Awesome Prometheus Alerts
- Loại bỏ hoàn toàn cấu hình monolithic quy tắc cảnh báo (trước đây lưu trong file duy nhất 47 KB `01-configmap-prometheus-rules.yaml`).
- Tách bạch và module hóa thành 8 tệp quy tắc theo miền chức năng (domain-driven) dưới thư mục `deploy/platform/metrics-thanos/rules/`, nạp tự động qua `configMapGenerator` vào ConfigMap `prometheus-rules`:
  1. `01-host-rules.yaml`: Quy tắc giám sát hạ tầng máy chủ, CPU, RAM, Disk, Inodes, Systemd services (`HostHighCpuLoad`, `HostOutOfMemory`, `HostOutOfDiskSpace`, `HostSystemdServiceCrashed`).
  2. `02-kubernetes-rules.yaml`: Quy tắc giám sát cụm Kubernetes, Pod CrashLoop, OOMKilled, Deployment/StatefulSet replicas mismatch (`KubernetesNodeReady`, `KubernetesPodCrashLooping`, `KubernetesDeploymentReplicasMismatch`, `KubernetesContainerOomKilled`).
  3. `03-mysql-rules.yaml`: Quy tắc giám sát cơ sở dữ liệu MySQL (`MysqlDown`, `MysqlTooManyConnections`, `MysqlSlowQueries`, `MysqlRestarted`).
  4. `04-jvm-rules.yaml`: Quy tắc runtime JVM Java (`JvmMemoryFillingUp`, `JvmGarbageCollectionDurationHigh`, `JvmThreadsDeadlocked`).
  5. `05-wan-network-rules.yaml`: Quy tắc suy giảm mạng WAN và độ trễ liên đám mây (`WanInterClusterLatencyHigh`, `WanPacketLossDetected`, `NetworkInterfaceErrorsHigh`, `CrossCloudWANLatencyDegraded`, `SpokeClusterHeartbeatAbsent`, `MicroserviceHighErrorRate`).
  6. `06-thanos-rules.yaml`: Quy tắc lưu trữ phân tán và compaction Thanos (`ThanosCompactHalted`, `ThanosCompactMultipleRunning`, `ThanosQueryHighErrorRate`).
  7. `07-cert-manager-rules.yaml`: Quy tắc quản lý chứng chỉ PKI và mTLS cert-manager (`CertManagerCertExpirySoon`, `CertManagerCertNotReady`, `CertManagerHittingRateLimits`).
  8. `08-opentelemetry-collector-rules.yaml`: Quy tắc đường ống dẫn dữ liệu viễn trắc OpenTelemetry Collector (`OtelCollectorQueueIsFillingUp`, `OtelCollectorDataDropped`, `OtelCollectorReceiverRefusedData`, `OtelCollectorMemoryHigh`).
- Khử trùng lặp tuyệt đối (deduplication) giữa Pyrra SLO Multi-Burn-Rate và cảnh báo ngưỡng: loại bỏ cảnh báo dư thừa `CrossClusterCallFailureRateHigh`, gắn cờ `MicroserviceHighErrorRate` ở mức `severity: info` và `strategy: signoz-diagnostic-only`.

## Consequences
### Tích cực (Positive)
- **Tập trung vào trải nghiệm người dùng thực:** Thay vì bận tâm về các cảnh báo tài nguyên không gây ảnh hưởng dịch vụ, kỹ sư chỉ nhận thông báo khi ngân sách lỗi của khách hàng thực sự bị đe dọa.
- **Rút ngắn tối đa thời gian khắc phục sự cố (MTTR):** Báo cáo Telegram đã có sẵn log lỗi và event, giúp chẩn đoán ngay lập tức trên thiết bị di động mà không cần đăng nhập máy trạm.
- **Loại bỏ tình trạng cảnh báo rác:** Cơ chế Multi-Burn-Rate và 60s cooldown buffer giúp giảm thiểu tới 85% số lượng thông báo không cần thiết so với cảnh báo ngưỡng tĩnh.

### Tiêu cực & Thách thức (Trade-offs)
- Cần thời gian huấn luyện đội ngũ kỹ sư để hiểu sâu sắc khái niệm SLI, SLO, Error Budget và cách tính toán burn rate.
- Robusta Runner tiêu tốn khoảng ~150–200 MB RAM trên cụm Hub.

## Alternatives considered
1. **Prometheus Alertmanager truyền thống không qua Robusta:** Cảnh báo khô khan, thiếu log và ngữ cảnh Kubernetes trực tiếp, buộc kỹ sư phải thao tác thủ công nhiều bước khi có sự cố.
2. **Cảnh báo ngưỡng tĩnh dựa trên CPU/RAM (Prometheus Rules thuần túy):** Thường xuyên gây báo động giả khi hệ thống chạy các tác vụ định kỳ (CronJobs) hoặc khi lưu lượng tăng tự nhiên nhưng ứng dụng vẫn phản hồi tốt.
3. **Các nền tảng thương mại (PagerDuty, Datadog):** Chi phí cấp phép bản quyền rất cao, không phù hợp cho đồ án học thuật và nghiên cứu nội bộ cục bộ.

## References
- Google Site Reliability Engineering (SRE) Workbook: Implementing SLOs and Alerting on SLOs
- Pyrra: Prometheus-based SLO Management Tool
- Robusta.dev: Kubernetes Observability and Automation Platform
- Prometheus Alertmanager Configuration Guide: Grouping and Inhibition Rules
