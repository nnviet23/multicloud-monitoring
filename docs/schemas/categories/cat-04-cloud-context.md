# Semantic Conventions: CAT-04 Cloud Infrastructure & Perimeter Context

**Status**: Stable (Core Cloud Attributes) / Experimental (Extended Identity & IAM)  
**Namespace**: `cloud.*`, `aws.*`, `azure.*`, `microsoft.entra.*`  
**OTel SemConv Domain**: `docs/resource/cloud-provider/`, `docs/azure/`, `docs/resource/`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-04` quy định chuẩn ngữ nghĩa ngữ cảnh hạ tầng đám mây (Cloud Infrastructure Metadata) và ranh giới quản trị danh tính/mạng (Perimeter Context).

Trong đồ án nghiên cứu nền tảng giám sát đa đám mây, các vi dịch vụ và thành phần lưu trữ phân tán giữa **AWS** (mô phỏng compute qua `aws-k3d`) và **Azure** (mô phỏng persistence qua `azure-k3d`). `CAT-04` cung cấp "tọa độ không gian đám mây" cho mọi tín hiệu telemetry (Metrics, Logs, Traces) thông qua 6 Trục Phụ Thuộc Đám Mây Sâu:
1. **Trục 1 - Nhà cung cấp & Vùng (Provider & Region):** Phân định ranh giới địa lý và pháp lý (`us-east-1` vs `southasia`).
2. **Trục 2 - Tài khoản & Thuê bao (Account & Subscription):** AWS Account ID 12 chữ số (`851725492014`) vs Azure Subscription UUID (`4b8f3a21-...`).
3. **Trục 3 - Quản trị Danh tính (IAM Role & Microsoft Entra ID):** AWS IAM Role ARN (IRSA) vs Microsoft Entra Tenant & User-Assigned Managed Identity (UAMI).
4. **Trục 4 - Định danh Tài nguyên Đám mây (Resource ID & ARN):** Định danh duy nhất toàn cầu cho tài nguyên (Pod / Node).
5. **Trục 5 - Ranh giới Mạng Đám mây (VPC / VNet & Subnet CIDR):** VPC ID vs VNet Name, Subnet Name, CIDR block.
6. **Trục 6 - Tường lửa & An ninh Mạng (Security Groups & NSG):** AWS SG ID vs Azure Network Security Group (NSG).

Telemetry của `CAT-04` được gắn tại Spoke Edge thông qua biến môi trường Pod và được làm giàu sâu (Synthetic Enrichment) tại Central Hub thông qua bộ xử lý OpenTelemetry Transformation Language (OTTL).

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `cloud.provider` | `cloud_provider` | Stable | Required [1] | string | Tên định danh nhà cung cấp dịch vụ đám mây. | `aws`, `azure`, `local` |
| `cloud.region` | `cloud_region` | Stable | Required [1] | string | Khu vực địa lý của trung tâm dữ liệu đám mây. | `us-east-1`, `southasia` |
| `cloud.availability_zone` | `cloud_zone` | Stable | Recommended | string | Vùng sẵn sàng độc lập bên trong Region. | `us-east-1a`, `southasia-1` |
| `cloud.account.id` | `cloud_account_id` | Stable | Required [2] | string | ID tài khoản đám mây (AWS Account ID hoặc Azure Subscription ID). | `851725492014`, `4b8f3a21-9e6c-4f80-b753-2d9a6e1c84f5` |
| `cloud.resource_id` | `cloud_resource_id` | Stable | Required [2] | string | Định danh tài nguyên toàn cầu (AWS ARN hoặc Azure Resource ID). | `arn:aws:eks:us-east-1:851725492014:pod/teastore/...` |
| `cloud.identity.arn` | `cloud_identity_arn` | Experimental | Recommended | string | Định danh danh tính bảo mật (AWS IAM Role ARN hoặc Azure UAMI ID). | `arn:aws:iam::851725492014:role/teastore-webui-irsa-role` |
| `microsoft.entra.tenant_id`| `entra_tenant_id` | Experimental | Recommended | string | Mã định danh thư mục Microsoft Entra ID (Azure AD Tenant). | `72f988bf-86f1-41af-91ab-2d7cd011db47` |
| `network.vpc.id` | `vpc_id` | Experimental | Recommended | string | Định danh mạng riêng ảo Amazon Virtual Private Cloud (VPC). | `vpc-0f8a3c2b1e7d9a4f6` |
| `network.vnet.id` | `vnet_id` | Experimental | Recommended | string | Định danh mạng riêng ảo Azure Virtual Network (VNet). | `vnet-teastore-southasia` |
| `network.subnet.id` | `subnet_id` | Experimental | Recommended | string | Định danh phân mạng con (Subnet ID / Subnet Name). | `subnet-09a8b7c6d5e4f3a21`, `snet-aks-nodepool-data` |
| `network.security_group.id`| `security_group_id`| Experimental | Recommended | string | Định danh nhóm bảo mật tường lửa (AWS Security Group hoặc Azure NSG). | `sg-01a2b3c4d5e6f7a8b`, `nsg-aks-teastore-internal` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc xuất hiện trên 100% telemetry để phục vụ gom nhóm đa đám mây (Multi-Cloud Fleet Aggregation).
- **[2]:** Được inject tự động tại Central Hub qua OTTL Statements trong `k8s/base/otel-collector/gateway/03-configmap.yaml` bóc tách theo cụm nguồn (`aws-k3d` vs `azure-k3d`).

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

Trong kiến trúc OpenTelemetry, các thuộc tính của `CAT-04` là **Resource Attributes** (thuộc tính định danh tài nguyên tĩnh), không sinh ra metric counter độc lập mà đóng vai trò là các chiều phân tích (dimensions/labels) trên các metric của Service Graph và Dashboards:

| Signal Role | TSDB Expression / Metric Usage | Description |
| :--- | :--- | :--- |
| **Service Graph Dimensions** | `traces_service_graph_request_total{client_cloud_provider!=server_cloud_provider}` | Đếm số lượng giao dịch đi xuyên biên giới giữa hai đám mây khác nhau. |
| **Cross-Cloud Latency** | `traces_service_graph_request_server_seconds_bucket{client_cloud_provider!=server_cloud_provider}` | Phân phối thời gian thực thi của các cuộc gọi liên đám mây (AWS $\rightarrow$ Azure). |
| **Fleet Infrastructure Count**| `count by (cloud_provider, cloud_region) (system_cpu_time_seconds_total{state="idle"})` | Đếm tổng số CPU Cores phân bổ theo từng nhà cung cấp và vùng đám mây. |
| **Topology Node Details** | Grafana Data Links & Interactive Fields: `cloud.identity.arn`, `network.vpc.id`, `network.subnet.id` | Hiển thị 10+ trường thông tin kiến trúc đám mây khi click vào Node trên Dashboard `02. Topology & Cloud Context`. |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuẩn hóa giá trị `cloud.provider` enum (`v1.21.0`):**
   - OTel quy định chặt chẽ các giá trị chuẩn: `aws`, `azure`, `gcp`, `alibaba_cloud`, `ibm_cloud`, `oracle_cloud`. Trong đồ án, chúng ta sử dụng chính xác `aws` và `azure` để đảm bảo tương thích 100% với các công cụ phân tích chuẩn quốc tế.
2. **Tiến hóa từ nhãn độc quyền sang OTel SemConv:**
   - Trong quá trình phát triển (ghi nhận tại `INC-P3-21`), đồ án đã xóa bỏ triệt để các nhãn phi tiêu chuẩn như `AzureVM` hoặc số ID giả lập phi thực tế (`123456789012` $\rightarrow$ `851725492014`, `00000000-...` $\rightarrow$ UUID thật), đưa toàn bộ về chuẩn Microsoft Entra ID và AWS ARN.

