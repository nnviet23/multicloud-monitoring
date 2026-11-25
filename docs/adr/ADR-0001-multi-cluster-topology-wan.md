# ADR-0001: Multi-Cluster Hub-Spoke Topology & WAN Network Emulation

## Status
Implemented (Đã triển khai)

## Context
Dự án nghiên cứu hệ thống Giám sát Đa đám mây và AIOps (Multi-Cloud Observability & AIOps) yêu cầu một môi trường kiểm thử cục bộ có khả năng mô phỏng chính xác topo đa đám mây phân tán trong giới hạn phần cứng máy trạm nhà phát triển (ngân sách tài nguyên 8–10 GB RAM). 

Hệ thống bao gồm 3 cụm Kubernetes độc lập:
1. `hub-k3d`: Cụm trung tâm (Hub cluster) đóng vai trò trung tâm điều khiển GitOps (Argo CD), hạ tầng giám sát tập trung (Thanos, Loki, Tempo, MinIO, Grafana, Pyrra, Robusta), và động cơ AIOps.
2. `aws-k3d`: Cụm Spoke mô phỏng môi trường AWS, vận hành các microservices tầng tính toán (compute workloads) của ứng dụng TeaStore (`webui`, `auth`, `recommender`, `image`, `registry`) cùng bộ sinh tải Locust.
3. `azure-k3d`: Cụm Spoke mô phỏng môi trường Azure, vận hành tầng lưu trữ dữ liệu bền vững (persistence & stateful workloads) của TeaStore (`persistence`, cơ sở dữ liệu `teastore-db` MySQL).

Các thách thức kỹ thuật cốt lõi cần giải quyết:
- **Kết nối mạng liên cụm (Cross-Cluster Interconnect):** Cần một mạng cầu nối Docker (Docker bridge network) độc lập với dải địa chỉ IP tĩnh cố định để đảm bảo định tuyến Layer 3 tin cậy giữa các container control plane của 3 cụm.
- **Phân giải tên miền liên cụm (Cross-Cluster DNS Resolution):** Các dịch vụ như OpenTelemetry Collector và Argo CD cần phân giải tên miền máy chủ qua lại giữa các cụm mà không cần cài đặt các giải pháp Service Mesh phức tạp gây tiêu tốn tài nguyên.
- **Mô phỏng mạng diện rộng WAN (WAN Network Emulation):** Môi trường thực tế giữa các nhà cung cấp đám mây (AWS, Azure) luôn chịu độ trễ (latency), dao động trễ (jitter), và mất gói tin (packet loss). Cần cơ chế đưa các tham số suy giảm mạng vào đường truyền liên cụm để đánh giá chính xác tác động lên luồng viễn trắc (telemetry stream) và độ trễ giao dịch.

## Decision
Chúng tôi quyết định chuẩn hóa cấu trúc topo mạng đa cụm và cơ chế mô phỏng WAN cục bộ như sau:

### 1. Dải mạng Docker Bridge chuyên dụng (Dedicated Docker Bridge)
- Khởi tạo một Docker network riêng biệt mang tên `mc-monitoring-net` với dải mạng:
  - **Subnet:** `172.28.0.0/16`
  - **Gateway:** `172.28.0.1`
- Gán địa chỉ IP tĩnh cố định cho các node control plane và LoadBalancer của từng cụm k3d:
  - `hub-k3d` (LoadBalancer Hub Gateway): `172.28.0.4` (hoặc IP định tuyến trên `mc-monitoring-net`)
  - `aws-k3d-server-0` / `azure-k3d-server-0`: cấp phát trong dải `172.28.0.0/16`

### 2. Phân giải tên miền qua CoreDNS NodeHosts
Thay vì triển khai các giải pháp Service Mesh nặng nề (như Istio Multi-Primary hay Linkerd Multi-Cluster), chúng tôi áp dụng cơ chế CoreDNS `NodeHosts` configmap:
- Khai báo ánh xạ tĩnh các hostname liên cụm vào CoreDNS của mỗi cụm:
  - `hub-gateway.hub.multicloud.local` -> IP LoadBalancer của `hub-k3d` (ví dụ `172.28.0.4`)
  - `thanos-query.hub.multicloud.local` -> IP LoadBalancer của `hub-k3d` (ví dụ `172.28.0.4`)
  - `hub.local` -> alias nội bộ cho Hub ingress/PKI SANs
- Cấu hình dịch vụ Hub Gateway trên `hub-k3d` để nhận luồng viễn trắc OTLP từ Spoke:
  - OTLP gRPC endpoint: `hub-gateway.hub.multicloud.local:4317` (Service type `LoadBalancer:4317` trỏ vào Hub OTel Gateway Service)
  - Argo CD Server endpoint: `hub.local:30443` / `localhost:8080` (port-forward)

### 3. Mô phỏng suy giảm mạng WAN bằng Linux Traffic Control (`tc netem`)
Để mô phỏng chân thực đường truyền Internet/WAN giữa các nhà cung cấp đám mây, chúng tôi áp dụng tiện ích kernel Linux `tc netem` (Network Emulator) trực tiếp trên interface mạng `eth0` của các container node k3d:
- **Độ trễ trung bình (Mean Delay):** `10ms delay`
- **Dao động trễ (Jitter):** `2ms jitter` (tuân theo phân phối Pareto hoặc Normal)
- **Tỷ lệ mất gói tin (Packet Loss):** `0.1% loss`
- Lệnh mẫu được cấu hình tự động qua CLI:
  ```bash
  tc qdisc add dev eth0 root netem delay 10ms 2ms loss 0.1%
  ```

### 4. Ngân sách tài nguyên (Resource Budget)
Tối ưu hóa tổng lượng RAM sử dụng của toàn bộ hệ sinh thái 3 cụm trong khoảng **7.7 – 9.7 GB RAM**:
- `hub-k3d`: Cấu hình Single-Replica cho toàn bộ control plane và platform pods (~4.2 – 5.2 GB RAM).
- `aws-k3d`: Vận hành 5 microservices TeaStore + OTel Javaagent (~2.2 – 2.8 GB RAM).
- `azure-k3d`: Vận hành TeaStore persistence + MySQL + OTel Collector (~1.3 – 1.7 GB RAM).

## Consequences
### Tích cực (Positive)
- **Môi trường lab có tính lặp lại 100%:** Bất kỳ nhà phát triển nào cũng có thể dựng hoàn chỉnh hệ thống 3 cụm k3d chỉ với một lệnh CLI hoặc `make infra`.
- **Phản ánh chân thực điều kiện mạng thực tế:** Việc mô phỏng độ trễ và mất gói tin qua `tc netem` giúp kiểm chứng cơ chế retry, backoff của OTel Collector và đánh giá thuật toán phân rã nguyên nhân gốc rễ (RCA) $T_{\text{WAN}}$.
- **Hiệu quả tài nguyên vượt trội:** Không phụ thuộc vào Service Mesh đắt đỏ, duy trì mức chiếm dụng RAM < 10 GB cho toàn bộ 3 cụm.

### Tiêu cực & Thách thức (Trade-offs)
- Cần quyền `NET_ADMIN` / đặc quyền root của Docker daemon để thực thi lệnh `tc` bên trong container k3d.
- Phải duy trì script đồng bộ CoreDNS khi IP hoặc hostname các node thay đổi.

## Alternatives considered
1. **Sử dụng dải mạng mặc định của Docker (Default Bridge):** Không đảm bảo IP cố định cho các cụm khi khởi động lại máy trạm, làm đứt gãy cấu hình endpoint liên cụm.
2. **Triển khai Istio Multi-Cluster Service Mesh:** Đạt tính năng tự động phát hiện dịch vụ nhưng tiêu tốn thêm ít nhất 3–4 GB RAM cho các Envoy sidecar proxy, vượt ngưỡng ngân sách phần cứng cục bộ.
3. **Triển khai trực tiếp trên Cloud thật (EKS & AKS):** Chi phí cao ($150–$300/tháng) và không phù hợp cho vòng lặp kiểm thử nhanh (rapid local iteration) ở giai đoạn nghiên cứu ban đầu.

## References
- Linux Advanced Routing & Traffic Control (LARTC) — Network Emulation (`tc netem`)
- K3d Official Documentation: Multi-Cluster Networking & Shared Docker Networks
- RFC 1918 — Address Allocation for Private Internals (`172.28.0.0/16`)
- SPEC RG TeaStore Benchmark Architecture Specification
