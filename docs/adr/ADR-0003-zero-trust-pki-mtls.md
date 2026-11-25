# ADR-0003: Zero-Trust PKI Infrastructure, Cross-Cluster mTLS 1.3 & Secret Encryption

## Status
Implemented (Đã triển khai)

## Context
Trong kiến trúc Multi-Cloud Hub-Spoke, dữ liệu viễn trắc (metrics, logs, traces) và các lệnh điều khiển điều phối phải di chuyển qua mạng diện rộng WAN mô phỏng giữa `aws-k3d`, `azure-k3d` và `hub-k3d`. Dữ liệu này có thể chứa thông tin cấu hình nhạy cảm, định danh cụm, hoặc dữ liệu nghiệp vụ khách hàng (PII).

Các yêu cầu an toàn thông tin cốt lõi:
1. **Bảo mật đường truyền liên đám mây (Cross-Cluster Transit Security):** Dữ liệu viễn trắc OpenTelemetry Protocol (OTLP) gRPC gửi từ các Spoke về Hub Gateway phải được mã hóa đầu cuối và xác thực hai chiều (Mutual TLS) để chống nghe lén (eavesdropping) và giả mạo (tampering/man-in-the-middle).
2. **Loại bỏ Reverse Proxy trung gian:** Tránh việc sử dụng các reverse proxy cồng kềnh (như Nginx hay Envoy ngoài rìa) làm điểm tắc nghẽn hiệu năng và tiêu tốn bộ nhớ; thay vào đó sử dụng tính năng mTLS gốc (native mTLS) tích hợp trực tiếp trong OpenTelemetry Collector.
3. **Quản lý vòng đời chứng chỉ số (Automated PKI Lifecycle):** Chứng chỉ số nội bộ phải được tự động cấp phát, quay vòng (rotate) và tái cấp phát mà không gây gián đoạn đường truyền viễn trắc.
4. **Bảo mật bí mật trong GitOps (GitOps Secret Management):** Mọi tài nguyên Kubernetes được quản lý theo mô hình GitOps trên Git repository công khai/bán công khai. Tuyệt đối không được lưu trữ thông tin nhạy cảm ở dạng bản rõ (plaintext).

## Decision
Chúng tôi quyết định thiết lập mô hình an ninh Zero-Trust cho toàn bộ hệ thống với ba trụ cột kỹ thuật:

### 1. Phân tầng Hạ tầng Khóa Công khai (Internal PKI Hierarchy) với cert-manager
- Triển khai **cert-manager `v1.16.2`** trên cụm `hub-k3d` kết hợp cấu hình phát hành chứng chỉ tự động:
  - **Root CA:** Khóa CA gốc nội bộ (`multicloud-root-ca`), lưu trữ bí mật an toàn với thời hạn 10 năm.
  - **Intermediate CAs / Issuers:** Cấp phát chứng chỉ ký số nội bộ cho từng thành phần (`hub-issuer`, `spoke-issuer`), đồng thời sinh chứng chỉ máy khách riêng cho từng Spoke (`aws-spoke-client-cert`, `azure-spoke-client-cert`).
- Quy định chứng chỉ máy chủ (Server Certificate) cho Hub OTel Gateway:
  - **Subject Alternative Names (SANs):** `hub-gateway.hub.multicloud.local`, `hub.local`, `*.hub.local`, `otel-gateway.monitoring.svc.cluster.local`, `172.28.0.4`.
  - **Thời hạn hiệu lực (Validity Duration):** 90 ngày (`2160h`).
  - **Ngưỡng quay vòng tự động (Automated Renewal):** Tự động tái cấp phát trước khi hết hạn 30 ngày (`renewBefore: 720h`).

### 2. Mã hóa Đường truyền Native mTLS 1.3 cho OTLP
Cấu hình giao thức xác thực hai chiều (Mutual TLS) trực tiếp trên OpenTelemetry Collector Exporters (tại Spoke) và Receivers (tại Hub):
- **Giao thức chuẩn:** Bắt buộc **TLS 1.3** (`min_version: "1.3"`).
- **Bộ mã hóa bảo mật cao (Cipher Suites):**
  - `TLS_AES_256_GCM_SHA384`
  - `TLS_CHACHA20_POLY1305_SHA256`
- **Cơ chế xác thực:**
  - Hub Gateway kiểm tra chứng chỉ máy khách (Client Certificate) từ Spoke dựa trên Root CA chung (`client_ca_file: /etc/otel/certs/ca.crt`).
  - Spoke Collectors kiểm tra chứng chỉ máy chủ của Hub Gateway (`ca_file: /etc/otel/certs/ca.crt`) và xác thực Server Name Indication (SNI).
- **Tránh Reverse Proxy trung gian:** Toàn bộ quá trình mã hóa/giải mã được xử lý ngay trong tiến trình Go của OTel Collector Contrib, tiết kiệm đáng kể CPU và giảm thêm độ trễ truyền gói tin.

### 3. Quản lý Bí mật Khai báo với Bitnami Sealed Secrets
- Triển khai **Bitnami Sealed Secrets (`sealed-secrets-controller`)** trên cụm Kubernetes với quy trình `kubeseal` sẵn sàng cho GitOps chính thức.
- Trong môi trường phát triển cục bộ không giao diện (local headless dev trên k3d), `infra/cli.py sync-secrets` hỗ trợ đồng bộ bí mật cục bộ nhanh chóng từ `.env` và chứng chỉ PKI mà không làm gián đoạn vòng lặp kiểm thử.
- Quy trình mã hóa GitOps chuẩn:
  - Khóa công khai (Public Key) của controller trên từng cụm được dùng để mã hóa bí mật từ môi trường phát triển cục bộ (`kubeseal --format yaml < secret.yaml > sealed-secret.yaml`).
  - Các tệp `SealedSecret` an toàn để lưu trữ công khai trên Git repository.
  - Controller bên trong từng cụm giải mã `SealedSecret` thành tài nguyên `Secret` tiêu chuẩn của Kubernetes bằng khóa bất đối xứng nội bộ mà không để lộ khóa ra ngoài.

## Consequences
### Tích cực (Positive)
- **Bảo mật cấp độ phòng thủ chuyên sâu (Defense-in-Depth):** Ngay cả khi đường truyền WAN mô phỏng bị bắt gói tin (packet sniffing qua Wireshark), toàn bộ dữ liệu viễn trắc OTLP đều được mã hóa bằng TLS 1.3 AES-256-GCM.
- **Tuân thủ nguyên tắc GitOps thuần khiết:** Toàn bộ cấu hình hệ thống bao gồm cả thông tin nhạy cảm đều có thể lưu trữ và đồng bộ an toàn qua Git nhờ Sealed Secrets.
- **Tối ưu hóa tài nguyên:** Giảm thiểu việc tiêu tốn RAM khi không phải chạy các bộ proxy phụ trợ như Nginx hay HAProxy bên ngoài OTel Collector.

### Tiêu cực & Thách thức (Trade-offs)
- Cần cơ chế phân phối an toàn chứng chỉ Root CA ban đầu và các cặp chứng chỉ mTLS cho các node k3d thông qua script tự động hóa khởi tạo nền tảng.
- Khi cần phục hồi thảm họa hoặc dựng lại cụm mới, khóa private key của Sealed Secrets Controller phải được sao lưu và phục hồi tương ứng.

## Alternatives considered
1. **Sử dụng WireGuard / IPSec VPN giữa các cụm:** Đem lại khả năng mã hóa toàn bộ lớp mạng Layer 3, tuy nhiên đòi hỏi cấu hình phức tạp trên host OS máy trạm và khó kiểm soát chi tiết chính sách mTLS cấp ứng dụng viễn trắc.
2. **Sử dụng HashiCorp Vault:** Cung cấp tính năng quản lý secret toàn diện nhưng đòi hỏi tài nguyên phần cứng lớn (~500MB – 1GB RAM), quá nặng so với ngân sách máy trạm địa phương 8–10 GB RAM.
3. **Mã hóa OTLP thông thường không dùng mTLS (chỉ dùng Server TLS):** Hub không thể xác thực được nguồn gốc dữ liệu gửi đến, dẫn đến rủi ro bị các Spoke giả mạo bơm dữ liệu rác làm sai lệch kết quả AIOps.

## References
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3
- OpenTelemetry Collector: Security Best Practices & TLS Configuration
- cert-manager Documentation: Certificate Lifecycle & X.509 Automation
- Bitnami Sealed Secrets: Encrypted Secrets for Kubernetes GitOps
