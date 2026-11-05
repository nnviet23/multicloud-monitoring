# Đề Xuất Giải Pháp Kỹ Thuật & Kế Hoạch Triển Khai (Technical Proposals & Solution Plan)

> **Tài liệu:** `docs/progress/02_solution_plan.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Cập nhật lần cuối:** 2026-11-04  
> **Quy tắc làm việc:** Tài liệu này ghi nhận toàn bộ các khúc mắc, câu trả lời phân tích chuyên sâu, thảo luận kỹ thuật, đề xuất giải pháp và kế hoạch hành động. **Chỉ tiến hành triển khai mã nguồn và cấu hình thực tế sau khi người dùng xem xét và phê duyệt các giải pháp trong tài liệu này.**

---

## Mục Lục Các Vấn Đề Bàn Luận (Discussion Index)

1. [Khúc mắc 1: Chi tiết hóa Topology Network đến cấp độ OpenStack / Azure Network Topology](#1-khúc-mắc-1-chi-tiết-hóa-topology-network-đến-cấp-độ-openstack--azure-network-topology)
2. [Khúc mắc 2: Hiện trạng Bucket `raw-telemetry` trong MinIO đang rỗng](#2-khúc-mắc-2-hiện-trạng-bucket-raw-telemetry-trong-minio-đang-rỗng)
3. [Khúc mắc 3: Sự phân mảnh nhãn Cluster (`cluster` vs `k8s_cluster_name`) và chuẩn hóa](#3-khúc-mắc-3-sự-phân-mảnh-nhãn-cluster-cluster-vs-k8s_cluster_name-và-chuẩn-hóa)
4. [Khúc mắc 4: Tiêu chuẩn Best Practice cho bộ Grafana Dashboards](#4-khúc-mắc-4-tiêu-chuẩn-best-practice-cho-bộ-grafana-dashboards)
5. [Kế hoạch hành động tổng thể chờ phê duyệt (Action Plan for Approval)](#5-kế-hoạch-hành-động-tổng-thể-chờ-phê-duyệt-action-plan-for-approval)

---

## 1. Khúc mắc 1: Chi tiết hóa Topology Network đến cấp độ OpenStack / Azure Network Topology

### 1.1. Bản chất sự khác biệt giữa hai loại Topology

Để xây dựng một sơ đồ trực quan và khoa học, chúng ta cần phân biệt rõ hai tầng kiến trúc mạng trong giám sát đa đám mây:

```
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG ỨNG DỤNG L7 (Application Service Graph Topology)                  │
│ • Đối tượng: Microservices (webui, auth, persistence, db)             │
│ • Giao thức: HTTP REST, gRPC, JDBC, Java RMI                           │
│ • Thông số: QPS (Request Rate), P90/P95 Latency, Error Rate, Traces    │
│ • Nguồn sinh: OpenTelemetry Traces + servicegraphconnector             │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ Chạy trên nền tảng
┌────────────────────────────────────▼───────────────────────────────────┐
│ TẦNG HẠ TẦNG MẠNG L3/L4 (Infrastructure Network & WAN Topology)        │
│ • Đối tượng: Cloud Providers, Clusters, Nodes, Subnets, Gateways       │
│ • Giao thức: IP, TCP/UDP, BGP, Overlay CNI (Flannel/Calico/Cilium)     │
│ • Thông số: IP src/target, Subnet CIDR, Packet Loss, RTT WAN, Jitter   │
│ • Nguồn sinh: Linux netem, Bridge Network, K8s CNI, Node Metrics       │
└────────────────────────────────────────────────────────────────────────┘
```

* **Mô hình OpenStack Network Topology / Azure Network Watcher:** Là bản đồ **L3/L4 Infrastructure Network**. Nó thể hiện Router, VNet/VPC, Subnet CIDR (ví dụ: `10.0.1.0/24`), Network Security Group (NSG), Card mạng ảo (vNIC), IP công cộng/riêng (Public/Private IP), và các Port kết nối.
* **Mô hình hiện tại của dự án trong Grafana:** Là bản đồ **L7 Application Service Graph**. Nó thể hiện luồng cuộc gọi giữa các dịch vụ microservice của TeaStore (`webui -> auth`, `webui -> persistence -> db`). Hiện tại, panel `nodeGraph` mới chỉ thể hiện `title` của node và đường liên kết cơ bản.

### 1.2. Khả năng đáp ứng yêu cầu của người dùng

**Hoàn toàn có thể làm được và làm rất chi tiết.** Chúng ta sẽ nâng cấp topology theo 2 giải pháp song hành:

#### Giải pháp 1.1: Làm giàu dữ liệu cho Grafana Node Graph (Enriched L7 Service Graph)
Grafana `nodeGraph` không chỉ hiển thị tên node mà hỗ trợ đầy đủ các trường dữ liệu trực quan mở rộng:
* **Tại mỗi Node (Microservice/Database):**
  * `mainStat`: Số lượng request gọi tới node (QPS hoặc Throughput, ví dụ: `45.2 req/s`).
  * `secondaryStat`: Thời gian phản hồi P95 hoặc P90 (ví dụ: `142 ms`).
  * `detail__ip`: Địa chỉ IP thực tế của Pod hoặc Service ClusterIP (ví dụ: `10.42.0.15`).
  * `detail__subnet`: Dải mạng Pod CIDR (`10.42.0.0/16`) hoặc Service CIDR (`10.43.0.0/16`).
  * `detail__cluster`: Cụm Kubernetes lưu trữ (`aws-k3d` hoặc `azure-k3d`).
  * `detail__cloud`: Nhãn nhà cung cấp đám mây (`AWS Simulation` hoặc `Azure Simulation`).
  * `arc__passed` / `arc__failed`: Vòng tròn Donut Chart hiển thị tỷ lệ thành công (màu xanh lá) và tỷ lệ lỗi (màu đỏ) ngay trên viền của icon node.
* **Tại mỗi Cạnh kết nối (Edge):**
  * `mainStat`: Lưu lượng request di chuyển trên đường truyền (`rate(traces_service_graph_request_total[5m])`).
  * `secondaryStat`: Độ trễ mạng và xử lý trên đường truyền (`request_server_seconds`).
  * `detail__source_ip`: IP nguồn phát sinh request.
  * `detail__target_ip`: IP đích tiếp nhận request.
  * `detail__wan_traversal`: Đánh dấu `true` nếu luồng đi xuyên qua WAN giả lập giữa AWS và Azure (RTT 10ms ±2ms, loss 0.1%).

#### Giải pháp 1.2: Bổ sung Dashboard Kiến Trúc Mạng L3/L4 (Multi-Cloud WAN & Infrastructure Topology)
Để đạt độ trực quan như OpenStack/Azure:
* Xây dựng một Dashboard chuyên biệt: **"Multi-Cloud Infrastructure Network & WAN Topology"**.
* Sử dụng panel **Grafana Canvas** hoặc **Node Graph** biểu diễn sơ đồ hạ tầng:
  * Khối **AWS Spoke Subnet**: Cụm `aws-k3d`, Bridge Subnet `172.28.0.0/16`, Pod CIDR `10.42.0.0/16`, Service NodePort `31112`.
  * Khối **Azure Spoke Subnet**: Cụm `azure-k3d`, Pod CIDR `10.42.0.0/16`, Service NodePort `31111`, MySQL Port `3306`.
  * Khối **Simulated WAN Gateway**: Đường truyền trung gian có tiêm trễ Linux `tc netem` (Latency: 10ms, Jitter: 2ms, Packet Loss: 0.1%).
  * Khối **Central Hub Ingestion**: Cụm `hub-k3d`, OTel Ingress mTLS 1.3 Port `4317/4318`.

---

## 2. Khúc mắc 2: Hiện trạng Bucket `raw-telemetry` trong MinIO đang rỗng

### 2.1. Phân tích nguyên nhân
Trong Phase 3, chúng ta đã khởi tạo 4 bucket trong MinIO S3:
1. `thanos-metrics`: Chứa các block TSDB nén của Prometheus đẩy qua Thanos Sidecar (đã có 24 block nén).
2. `loki-data`: Chứa các chunks dữ liệu log TSDB của Loki (đang hoạt động).
3. `tempo-traces`: Chứa các parquet block của trace từ Tempo (đang hoạt động).
4. `raw-telemetry`: Hiện đang rỗng 0 bytes.

**Lý do:** Bucket `raw-telemetry` được định nghĩa trong kiến trúc ban đầu nhằm đóng vai trò **Data Lake lưu trữ telemetry gốc bất biến (Immutable Raw Telemetry)** để phục vụ lưu trữ dài hạn, kiểm tra tính toàn vẹn benchmark và làm tập dữ liệu huấn luyện mô hình AI offline ở Phase sau.
Hiện tại, pipeline của Hub OTel Collector (`otel-collector-hub`) mới chỉ cấu hình 3 luồng xuất (exporters):
* Metrics -> Exporter `prometheus` (trên cổng `8889`)
* Traces -> Exporter `otlp/tempo` (trên cổng `4317`)
* Logs -> Exporter `loki` (trên cổng `3100`)

Hub Collector **chưa kích hoạt exporter lưu file S3 trực tiếp** vào bucket `raw-telemetry`.

### 2.2. Đề xuất giải pháp
* Tích hợp exporter `awss3` hoặc `file` exporter kết hợp luồng OTel Gateway tại Hub.
* Cấu hình exporter định kỳ đẩy các mẻ (batch) telemetry thô dạng nén JSON/Protobuf/Parquet trực tiếp vào MinIO S3 theo đường dẫn phân cấp thời gian:
  ```
  s3://raw-telemetry/spoke=aws/year=2026/month=11/day=04/traces_raw_*.json.gz
  s3://raw-telemetry/spoke=azure/year=2026/month=11/day=04/logs_raw_*.json.gz
  ```
* Bằng cách này, bucket `raw-telemetry` sẽ luôn có dữ liệu thô phục vụ tái lập thí nghiệm và đánh giá độ chính xác (Accuracy) theo hợp đồng dữ liệu.

---

## 3. Khúc mắc 3: Sự phân mảnh nhãn Cluster (`cluster` vs `k8s_cluster_name`) và chuẩn hóa

### 3.1. Phân tích nguyên nhân người dùng thấy 2 nhãn khác nhau
Người dùng đặt câu hỏi rất chuẩn xác: *"Tại sao khi filter metric lại có 2 loại nhãn: filter theo `cluster` thì có `hub-k3d`, còn filter theo `k8s_cluster_name` thì có `aws-k3d` và `azure-k3d`? Tại sao không chuẩn hóa lại thành một?"*

Nguyên nhân xuất phát từ sự khác biệt giữa hai nguồn cào dữ liệu trong Phase 3:
1. **Nguồn 1 (Dữ liệu từ Spoke - AWS & Azure):** Đi qua OpenTelemetry Collector. Chuẩn OpenTelemetry Semantic Conventions quy định nhãn cụm Kubernetes là `k8s.cluster.name`. Khi exporter `prometheus` chuyển đổi sang định dạng nhãn của Prometheus, dấu chấm được đổi thành dấu gạch dưới: `k8s_cluster_name`.
2. **Nguồn 2 (Dữ liệu nội bộ cụm Hub):** Được Prometheus cào trực tiếp từ các Pod nội bộ (`tempo`, `loki`, `minio`, và chính `prometheus`). Trong file `prometheus.yml`, khối `external_labels` khai báo:
   ```yaml
   global:
     external_labels:
       cluster: hub-k3d
   ```
   Do đó, các metric nội bộ của Hub chỉ mang nhãn `cluster="hub-k3d"` chứ không có `k8s_cluster_name`.
3. Khi chúng ta thực hiện fix nhanh trước đó, ta gán thêm `attributes["cluster"]` trong OTel Hub. Kết quả là Spoke có cả 2 nhãn (`cluster` và `k8s_cluster_name`), trong khi Hub chỉ có nhãn `cluster`.

### 3.2. Đề xuất chuẩn hóa triệt để (Single Source of Truth)
Để loại bỏ hoàn toàn sự phân mảnh, thống nhất đúng chuẩn OpenTelemetry Semantic Conventions trên toàn bộ hệ thống:

* **Quy chuẩn duy nhất:** Chuẩn hóa toàn bộ hệ thống sử dụng nhãn chính thức:
  * `k8s_cluster_name`: Nhận các giá trị `hub-k3d`, `aws-k3d`, `azure-k3d`.
  * `cloud_provider`: Nhận các giá trị `hub` (hoặc `local`), `aws`, `azure`.
* **Hành động cụ thể:**
  1. Trong `k8s/base/metrics-thanos/01-configmap-prometheus.yaml`:
     Đổi `external_labels` của Prometheus thành:
     ```yaml
     global:
       external_labels:
         k8s_cluster_name: hub-k3d
         cloud_provider: hub
     ```
  2. Bổ sung cấu hình relabeling trong Prometheus để tự động alias `cluster -> k8s_cluster_name` cho tất cả các scrape jobs nội bộ.
  3. Trong `k8s/base/otel-collector/gateway/03-configmap.yaml`:
     Đảm bảo OTTL chỉ sinh `k8s_cluster_name` và `cloud_provider`, xóa bỏ các nhãn dư thừa cũ.
* **Kết quả sau chuẩn hóa:** Khi vào Grafana Explore hoặc Pyrra, người dùng chỉ cần chọn một nhãn duy nhất `k8s_cluster_name` để lọc trọn vẹn cả 3 cụm: `hub-k3d`, `aws-k3d`, `azure-k3d`.

---

## 4. Khúc mắc 4: Tiêu chuẩn Best Practice cho bộ Grafana Dashboards

### 4.1. Thực trạng hiện tại
Hiện tại hệ thống mới chỉ có 2 dashboards cơ bản:
1. `Multi-Cloud System Topology & Service Graph` (`mc-system-topology`)
2. `TeaStore Multi-Cloud RED Metrics` (`mc-red-metrics`)

### 4.2. Tiêu chuẩn Best Practice ngành (Industry Standard & Google SRE)
Trong vận hành hệ thống phân tán và đa đám mây, các tổ chức lớn (Google SRE, Uber, Netflix, Grafana Labs) áp dụng **Mô hình Kim tự tháp Giám sát (Monitoring Pyramid)**. Hệ thống không nên dồn tất cả thông tin vào một màn hình duy nhất (gây quá tải thị giác và làm chậm truy vấn), mà được chia thành **6 đến 7 Dashboards chuyên biệt** theo từng vai trò (Personas):

```
                      ▲
                     / \     TẦNG 1: EXECUTIVE FLEET OVERVIEW
                    /   \    (Dành cho Lãnh đạo / SRE Lead)
                   /─────\
                  /       \   TẦNG 2: SERVICE TOPOLOGY & RED METRICS
                 /         \  (Dành cho SRE / DevOps phát hiện sự cố)
                /───────────\
               /             \ TẦNG 3: CLUSTER CAPACITY & WAN INFRASTRUCTURE
              /               \(Dành cho Cloud Admin / SysAdmin phân tích tài nguyên)
             /─────────────────\
            /                   \TẦNG 4: DEEP DIVE LOGS & DISTRIBUTED TRACING
           /─────────────────────\(Dành cho Developer / SRE điều tra mã lỗi gốc)
```

### 4.3. Danh mục 7 Dashboards đề xuất triển khai

| STT | Tên Dashboard đề xuất | Mã UID | Mục đích & Vấn đề giải quyết | Các Panels / Metrics cốt lõi |
|---|---|---|---|---|
| **01** | **Multi-Cloud Executive Fleet Overview** | `mc-executive-overview` | Cung cấp cái nhìn toàn cảnh cấp cao nhất về độ khả dụng của toàn bộ các đám mây, SLA/SLO tổng thể, tổng số cụm, tổng traffic và số lượng cảnh báo active. | • Tổng quan trạng thái 3 cụm (Hub, AWS, Azure)<br>• Tỷ lệ đạt SLO toàn hệ thống (99.5%)<br>• Tổng QPS & Tỷ lệ lỗi toàn cầu<br>• Số lượng cảnh báo Robusta đang kích hoạt |
| **02** | **Cross-Cloud Topology & Service Flow** | `mc-system-topology` | Trực quan hóa kiến trúc microservice, sơ đồ luồng dữ liệu liên đám mây AWS <-> Azure, độ trễ và lưu lượng trên từng tuyến kết nối mạng. | • Node Graph chi tiết (QPS, P95, IP, Subnet, Status Arc)<br>• Băng thông cuộc gọi xuyên WAN AWS -> Azure<br>• Phân bổ cuộc gọi theo giao thức (HTTP, JDBC, RMI) |
| **03** | **Application RED & Golden Signals** | `mc-red-metrics` | Theo dõi 4 tín hiệu vàng (Google Golden Signals) cho từng microservice của TeaStore (`webui`, `auth`, `persistence`, `db`, v.v.). | • **Rate:** Số request/giây trên từng service<br>• **Errors:** Tỷ lệ mã lỗi HTTP 5xx, 4xx<br>• **Duration:** Biểu đồ nhiệt độ trễ P50, P90, P99<br>• **Saturation:** Mức độ nghẽn hàng đợi Tomcat/HikariCP |
| **04** | **Multi-Cloud K8s Node & Pod Capacity** | `mc-k8s-infrastructure` | Giám sát tài nguyên hạ tầng máy chủ và container trên cả 3 cụm Kubernetes, phát hiện sớm nguy cơ thiếu hụt CPU/RAM. | • Sử dụng CPU & Memory theo cụm (`aws`, `azure`, `hub`)<br>• Tần suất Pod restart và biến cố OOMKilled<br>• Lưu lượng mạng I/O (RX/TX bytes/sec) trên từng node<br>• Trạng thái đĩa cứng & Storage IOPS của PVC |
| **05** | **SLO Management & Error Budget** | `mc-slo-governance` | Tích hợp sâu với Pyrra để theo dõi ngân sách lỗi (Error Budget), cảnh báo tốc độ đốt ngân sách (Burn Rate) theo chuẩn SRE. | • Trạng thái tuân thủ SLO TeaStore 99.5% 28 ngày<br>• Ngân sách lỗi còn lại (Remaining Error Budget %)<br>• Tốc độ đốt lỗi đa khung giờ (1h, 6h, 24h Burn Rate)<br>• Dự báo thời điểm vi phạm SLA |
| **06** | **Simulated WAN Network Emulation** | `mc-wan-telemetry` | Giám sát chất lượng đường truyền mạng mô phỏng giữa AWS và Azure qua các thông số tiêm suy hao của Linux `tc netem`. | • RTT Latency thực tế giữa AWS và Azure (mục tiêu: 10ms ±2ms)<br>• Mức độ biến thiên độ trễ (Jitter: 2ms)<br>• Tỷ lệ rớt gói tin đo lường (Packet Loss: 0.1%)<br>• Băng thông tiêu thụ đường truyền WAN |
| **07** | **Centralized Logs & Tracing Correlation** | `mc-logs-traces-deepdive` | Phối hợp tìm nguyên nhân gốc rễ (RCA) bằng cách liên kết trực tiếp giữa Log (Loki) và Trace (Tempo). | • Biểu đồ khối lượng log theo mức độ (Error, Warn, Info)<br>• Tìm kiếm log theo Service và Trace ID<br>• Waterfall Trace Spans của các giao dịch lỗi<br>• Danh sách các câu truy vấn MySQL chậm nhất |

---

## 5. Kế Hoạch Hành Động Chi Tiết (Action Plan for Approval)

Dưới đây là kế hoạch 4 bước cụ thể chuẩn bị triển khai. **Kính gửi bạn xem xét và phê duyệt trước khi thực thi:**

```
┌────────────────────────────────────────────────────────────────────────┐
│ BƯỚC 1: CHUẨN HÓA NHÃN CỤM METRICS                                    │
│ • Sửa prometheus.yml: external_labels -> k8s_cluster_name: hub-k3d     │
│ • Đồng bộ OTTL Processor tại Hub: k8s_cluster_name và cloud_provider   │
│ • Kiểm thử PromQL: Chỉ dùng 1 nhãn duy nhất cho toàn bộ 3 cụm          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ BƯỚC 2: NÂNG CẤP RICH TOPOLOGY NETWORK PANEL                           │
│ • Bổ sung mainStat (QPS), secondaryStat (P95 Latency) vào node & edge  │
│ • Bổ sung detail__ip, detail__cluster, detail__cloud, detail__subnet   │
│ • Bổ sung arc__passed và arc__failed (vòng tròn tỷ lệ lỗi)             │
│ • Thêm Panel bản đồ hạ tầng L3/L4 (WAN Emulation & Bridge Subnets)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ BƯỚC 3: KÍCH HOẠT DUMP TELEMETRY VÀO BUCKET RAW-TELEMETRY             │
│ • Cấu hình exporter awss3/file tại OTel Hub Collector                  │
│ • Đẩy telemetry thô dạng nén vào s3://raw-telemetry/                  │
│ • Xác thực bucket raw-telemetry có dữ liệu bằng lệnh mc ls             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ BƯỚC 4: TRIỂN KHAI BỘ 7 GRAFANA DASHBOARDS CHUẨN SRE                  │
│ • Viết các manifest JSON dashboards: 01, 04, 05, 06, 07                │
│ • Cập nhật Kustomize ConfigMap Generator tự động nạp vào Grafana       │
│ • Kiểm tra hiển thị và tính toán số liệu trên Web GUI                  │
└────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Trạng thái:** Kế hoạch trên đã sẵn sàng. Khi bạn xem qua các giải pháp và đồng ý với hướng tiếp cận, bạn chỉ cần phản hồi chấp thuận, mình sẽ lập tức bắt tay vào thực hiện từng bước chính xác và an toàn!

