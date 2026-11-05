# Chiến Lược Giám Sát Tài Nguyên, Độ Phủ & Ma Trận Phụ Thuộc Đám Mây Sâu (Deep Resource Monitoring, Coverage & Cloud Dependencies)

> **Tài liệu tham chiếu:** `docs/progress/03_resource_monitor.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Phiên bản:** v2.0.0 (Deep Cloud Dependencies Edition)  
> **Cập nhật lần cuối:** 2026-11-04  
> **Mục tiêu:** Định hình mô hình giám sát 360 độ đi sâu vào **Cloud Dependencies của từng tài nguyên cá thể (Single Resource Cloud Dependencies)**: mở rộng từ định danh IAM (Roles, Policies, Service Principals, Managed Identities), Định danh tài nguyên ARN ID (`cloud.resource_id`), Định danh tài khoản (`cloud.account.id`), Mạng & Chu vi bảo mật (VPC/VNet, Subnets, Route Tables, Security Groups, ENI), Lưu trữ & Mật mã (EBS, Managed Disks, KMS Key ARN, Key Vault URI) đến Quản trị & Nhật ký kiểm toán; chuẩn hóa toàn diện theo chuẩn OpenTelemetry Semantic Conventions; loại bỏ triệt để tình trạng `unknown_service`.

---

## 1. Bản Đồ Phụ Thuộc Đám Mây Sâu Của Một Tài Nguyên (Single-Resource 360° Cloud Dependency Model)

### 1.1. Khái niệm và Tầm nhìn Kiến trúc
Trong các hệ thống giám sát truyền thống, việc giám sát một tài nguyên tính toán (ví dụ: một Pod hay một Container) thường chỉ dừng lại ở các chỉ số cục bộ của Kubernetes (CPU, RAM, Pod Name, Namespace). Tuy nhiên, trong môi trường Đa đám mây (Multi-Cloud) cấp doanh nghiệp, một tài nguyên **không bao giờ tồn tại cô lập**.

Một tài nguyên duy nhất (Single Resource) luôn được neo chặt vào một hệ sinh thái **6 Trục Phụ Thuộc Đám Mây Cơ Sở (6 Foundational Cloud Vectors)**:
1. **Trục Định Danh & Cấp Quyền (Identity & Access Vector - IAM / Entra ID):** Các IAM Role, Chính sách Policy, Instance Profile, Managed Identity, OIDC Provider, ServiceAccount IRSA.
2. **Trục Chu Vi Mạng & Định Tuyến (Network & Traffic Perimeter Vector):** VPC / VNet ID, Subnet ID, Route Table ID, Security Group / NSG, Network Interface (ENI), Private Endpoint, Internet/NAT Gateway.
3. **Trục Lưu Trữ Khối & Dữ Liệu (Storage & Persistence Vector):** EBS Volume ID, Azure Managed Disk ID, File Systems (EFS/Azure Files), Object Storage S3/Blob.
4. **Trục Bảo Mật Mật Mã & Bí Mật (Cryptography & Secrets Vector):** KMS Key ARN, Key Vault CMK URI, Secrets Manager Secret ARN.
5. **Trục Máy Chủ Tính Toán & Điều Phối (Compute & Platform Vector):** Host / VM Instance ID, AMI / Image URN, Node Pool, Placement Group, CNI IPAM, Linux Kernel/cgroups.
6. **Trục Quản Trị, Chi Phí & Kiểm Toán (Governance, Billing & Audit Vector):** Cloud Account ID, Subscription ID, Resource Group, CloudTrail / Activity Log, CloudWatch / Log Analytics Workspace, Thẻ gắn nhãn chi phí (Cost Allocation Tags).

```
                                      ┌──────────────────────────────────────────────────────────────┐
                                      │              6. GOVERNANCE, AUDIT & COST                     │
                                      │ • cloud.account.id: 123456789012 / Subscription ID           │
                                      │ • CloudTrail Trail ARN / Azure Activity Log                  │
                                      │ • Tags: CostCenter, Environment, Owner, Project             │
                                      └──────────────────────────────┬───────────────────────────────┘
                                                                     │
                                      ┌──────────────────────────────┴───────────────────────────────┐
                                      │             1. IDENTITY & ACCESS (IAM / ENTRA ID)            │
                                      │ • cloud.identity.arn: arn:aws:iam::...:role/webui-irsa-role   │
                                      │ • IAM Policy ARNs, Managed Identity Client/Principal ID     │
                                      │ • K8s ServiceAccount IRSA OIDC Token                         │
                                      └──────────────────────────────┬───────────────────────────────┘
                                                                     │
   ┌─────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┐
   │                                                                 │                                                                 │
┌──▼────────────────────────────────────────────────────────┐        │        ┌────────────────────────────────────────────────────────▼──┐
│             2. NETWORK & SECURITY PERIMETER               │        │        │               4. CRYPTOGRAPHY & SECRETS                   │
│ • network.vpc.id: vpc-0a1b2c3d4e5f67890 (CIDR: 10.0.0.0/16)│        │        │ • security.kms.key_arn: arn:aws:kms:...:key/1234abcd      │
│ • network.subnet.id: subnet-0e1f2a3b (10.0.1.0/24 App Sub) │        │        │ • Azure Key Vault Key URI: https://kv-.../keys/...        │
│ • network.security_group.id: sg-0c4d5e6f (App SG: 8080)   │        │        │ • security.secrets.arn: arn:aws:secretsmanager:...:secret │
│ • network.interface.id: eni-0a112233 (Primary IPAM NIC)   │        │        │ • Transparent Data Encryption (TDE) CMK State             │
│ • Route Table ID, NAT Gateway ID, NACL ID                 │        │        │                                                           │
└──┬────────────────────────────────────────────────────────┘        │        └────────────────────────────────────────────────────────┬──┘
   │                                                                 │                                                                 │
   │                                  ┌──────────────────────────────▼───────────────────────────────┐                                 │
   │                                  │          ★ TÀI NGUYÊN TRUNG TÂM (CENTER RESOURCE) ★          │                                 │
   │                                  │                                                              │                                 │
   │                                  │  • cloud.resource_id:                                        │                                 │
   │                                  │    arn:aws:eks:us-east-1:123456789012:pod/...                │                                 │
   │                                  │    hoặc Azure Resource ID đầy đủ                             │                                 │
   │                                  │  • service.name: teastore-webui / teastore-db                │                                 │
   │                                  │  • k8s.pod.ip: 10.42.0.10 | NodePort: 31112/31111           │                                 │
   │                                  └──────────────────────────────┬───────────────────────────────┘                                 │
   │                                                                 │                                                                 │
   │                                                                 │                                                                 │
┌──▼────────────────────────────────────────────────────────┐        │        ┌────────────────────────────────────────────────────────▼──┐
│              3. STORAGE & DATA PERSISTENCE                │        │        │              5. COMPUTE, HOST & PLATFORM                  │
│ • storage.volume.id: vol-0123456789abcdef0 (AWS EBS gp3)  │        │        │ • host.id: i-0a1b2c3d4e5f67890 (EC2 / VM Instance ID)     │
│ • Azure Managed Disk ID: /subscriptions/.../disks/...     │        │        │ • host.type: m5.xlarge / Standard_D4s_v5                  │
│ • Volume IOPS: 3000, Throughput: 125 MB/s, Encrypted: true │        │        │ • host.image.id: ami-0c55b159cbfafe1f0                    │
│ • storage.bucket: s3://raw-telemetry / thanos-metrics     │        │        │ • k8s.node.name: k3d-aws-k3d-server-0                     │
│ • Mount Path: /var/lib/mysql, /var/log/pods               │        │        │ • Availability Zone: us-east-1a / southasia-1             │
└───────────────────────────────────────────────────────────┘        │        └───────────────────────────────────────────────────────────┘
                                                                     │
                                      ┌──────────────────────────────┴───────────────────────────────┐
                                      │             APPLICATION & SYSTEM DEPENDENCIES                │
                                      │ • Upstream Ingress: Client IP / Ingress Controller           │
                                      │ • Downstream Services: teastore-auth, image, persistence    │
                                      │ • Database: MySQL 8.0 TCP :3306 (teastore-db)                │
                                      │ • Registry: Java RMI :1099 (teastore-registry)               │
                                      └──────────────────────────────────────────────────────────────┘
```

---

## 2. Đi Sâu Vào Hai Tài Nguyên Đại Diện Của Hệ Thống

Để thể hiện chi tiết chiều sâu phụ thuộc không giới hạn, chúng ta mô hình hóa 2 tài nguyên đóng vai trò then chốt trong kiến trúc Multi-Cloud TeaStore:

### 2.1. Phụ Thuộc Đám Mây Sâu Của Tài Nguyên Tính Toán AWS (`teastore-webui`)

Tài nguyên `teastore-webui` được triển khai tại Spoke `aws-k3d` (mô phỏng AWS EKS chạy trên EC2 Instances):

```
                                  CÂY PHỤ THUỘC ĐÁM MÂY (AWS EKS WORKLOAD)
                                     Tài nguyên: teastore-webui Pod
                                                     │
 ┌───────────────────────────────────────────────────┼───────────────────────────────────────────────────┐
 │ [1] IDENTITY & ACCESS MANAGEMENT (IAM)            │ [2] NETWORKING & SECURITY PERIMETER               │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • cloud.account.id: "123456789012"                │ • network.vpc.id: "vpc-0a1b2c3d4e5f67890"         │
 │ • cloud.identity.arn:                             │ • network.subnet.id: "subnet-0e1f2a3b4c5d6e7f8"   │
 │   "arn:aws:iam::123456789012:role/teastore-webui" │   (Private App Subnet, CIDR: 10.0.1.0/24)         │
 │ • IAM Role Name: "teastore-webui-irsa-role"       │ • network.security_group.id:                      │
 │ • Attached Managed Policies:                      │   "sg-0c4d5e6f7a8b9c0d1" (teastore-webui-sg)      │
 │   - arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess│ • Cluster Security Group:                         │
 │   - arn:aws:iam::123456789012:policy/AppSecrets   │   "sg-0987654321fedcba0" (eks-cluster-sg)         │
 │ • OIDC Issuer:                                    │ • Elastic Network Interface (ENI):                │
 │   "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED..."│   "eni-0a112233445566778"                         │
 │ • K8s ServiceAccount: "teastore-webui-sa"         │ • Route Table: "rtb-0123456789abcdef0"            │
 │ • IRSA Projected Token:                           │ • NAT Gateway: "nat-0123456789abcdef0"            │
 │   "/var/run/secrets/eks.amazonaws.com/serviceaccount" • Network ACL: "acl-0123456789abcdef0"          │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ [3] COMPUTE, HOST & PLACEMENT                     │ [4] STORAGE & CRYPTOGRAPHY                        │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • cloud.resource_id:                              │ • storage.volume.id: "vol-0123456789abcdef0"      │
 │   "arn:aws:eks:us-east-1:123456789012:pod/..."    │ • Volume Type: "gp3" (IOPS: 3000, 125 MB/s)       │
 │ • host.id: "i-0a1b2c3d4e5f67890"                  │ • Encrypted: true                                 │
 │ • host.type: "m5.xlarge" (4 vCPU, 16 GiB RAM)     │ • security.kms.key_arn:                           │
 │ • host.image.id: "ami-0c55b159cbfafe1f0"          │   "arn:aws:kms:us-east-1:123456789012:key/..."    │
 │ • cloud.region: "us-east-1"                       │ • security.secrets.arn:                           │
 │ • cloud.availability_zone: "us-east-1a"           │   "arn:aws:secretsmanager:us-east-1:123456789012: │
 │ • EC2 Placement Group: "pg-teastore-compute"      │   secret:teastore/app-secrets-ab12cd"             │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ [5] GOVERNANCE, AUDIT & COST                      │ [6] RUNTIME & CONTAINER PLATFORM                  │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • CloudWatch Log Group:                           │ • k8s.cluster.name: "aws-k3d"                     │
 │   "arn:aws:logs:us-east-1:123456789012:log-group: │ • k8s.namespace.name: "teastore"                  │
 │   /aws/eks/teastore-cluster/cluster"              │ • k8s.pod.name: "teastore-webui-74c575bf78-5kldb" │
 │ • CloudTrail Trail ARN:                           │ • k8s.container.name: "teastore-webui"            │
 │   "arn:aws:cloudtrail:us-east-1:123456789012:     │ • k8s.pod.ip: "10.42.0.10"                        │
 │   trail/management-events"                        │ • Container Runtime: "containerd://1.7.11"        │
 │ • Tag CostCenter: "CC-ENGINEERING-402"            │ • Process User: "tomcat (UID: 1000)"              │
 │ • Tag Environment: "production-simulation"        │ • JVM Version: "OpenJDK 64-Bit Server 11.0.16"    │
 └───────────────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

---

### 2.2. Phụ Thuộc Đám Mây Sâu Của Tài Nguyên Dữ Liệu Azure (`teastore-db`)

Tài nguyên `teastore-db` là trái tim dữ liệu của hệ thống, triển khai tại Spoke `azure-k3d` (mô phỏng Azure Database for MySQL Flexible Server hoặc AKS StatefulSet gắn Azure Managed Disk):

```
                                  CÂY PHỤ THUỘC ĐÁM MÂY (AZURE DATA WORKLOAD)
                                       Tài nguyên: teastore-db (MySQL 8.0)
                                                     │
 ┌───────────────────────────────────────────────────┼───────────────────────────────────────────────────┐
 │ [1] IDENTITY & ACCESS MANAGEMENT (ENTRA ID)       │ [2] NETWORKING & PERIMETER SECURITY               │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • cloud.account.id: (Subscription ID)             │ • network.vnet.id:                                │
 │   "00000000-0000-0000-0000-000000000000"          │   "/subscriptions/.../virtualNetworks/            │
 │ • Directory (Tenant) ID:                          │   vnet-teastore-southasia"                        │
 │   "11111111-2222-3333-4444-555555555555"          │ • network.subnet.id:                              │
 │ • User-Assigned Managed Identity ID:              │   "/subscriptions/.../subnets/                    │
 │   "/subscriptions/.../providers/                  │   snet-mysql-delegated" (CIDR: 10.1.2.0/24)       │
 │   Microsoft.ManagedIdentity/userAssignedIdentities│ • Network Security Group (NSG) ID:                │
 │   /uami-teastore-db"                              │   "/subscriptions/.../networkSecurityGroups/      │
 │ • Managed Identity Client ID:                     │   nsg-mysql-internal"                             │
 │   "22222222-3333-4444-5555-666666666666"          │ • Private Endpoint NIC Resource ID:               │
 │ • Managed Identity Principal (Object) ID:         │   "/subscriptions/.../networkInterfaces/          │
 │   "33333333-4444-5555-6666-777777777777"          │   nic-pe-teastore-db"                             │
 │ • RBAC Role: "Key Vault Crypto Service Encryption │ • Private DNS Zone:                               │
 │   User" trên Key Vault dữ liệu                    │   "privatelink.mysql.database.azure.com"          │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ [3] COMPUTE, HOST & PLACEMENT                     │ [4] STORAGE & CRYPTOGRAPHY                        │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • cloud.resource_id: (Full Azure Resource ID)     │ • storage.volume.id:                              │
 │   "/subscriptions/00000000-0000-0000-0000-        │   "/subscriptions/.../providers/                  │
 │   000000000000/resourceGroups/rg-teastore-       │   Microsoft.Compute/disks/disk-teastore-db-data"  │
 │   southasia/providers/Microsoft.DBforMySQL/       │ • Disk SKU: "Premium_LRS" (SSD, 256 GiB)          │
 │   flexibleServers/teastore-db"                    │ • Disk Encryption Set ID:                         │
 │ • host.type: "Standard_D4ds_v5" (4 vCPU, 16 GB)   │   "/subscriptions/.../diskEncryptionSets/des-db"  │
 │ • cloud.region: "southasia" (Singapore/India)     │ • Customer-Managed Key (CMK) URI:                 │
 │ • cloud.availability_zone: "southasia-1"          │   "https://kv-teastore-southasia.vault.azure.net/ │
 │ • Azure Resource Group: "rg-teastore-southasia"   │   keys/teastore-db-cmk/4321abcd4321abcd"          │
 │ • Fault Domain: "FD-0", Update Domain: "UD-0"     │ • Transparent Data Encryption (TDE): "Enabled"    │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ [5] GOVERNANCE, AUDIT & DIAGNOSTICS               │ [6] ENGINE & RUNTIME PLATFORM                     │
 ├───────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
 │ • Log Analytics Workspace ID:                     │ • db.system: "mysql"                              │
 │   "/subscriptions/.../providers/                  │ • db.version: "8.0.35"                            │
 │   Microsoft.OperationalInsights/workspaces/law-ts"│ • db.name: "teadb"                                │
 │ • Diagnostic Settings ID:                         │ • net.peer.port: 3306                             │
 │   "diag-teastore-db-all-logs-and-metrics"         │ • InnoDB Buffer Pool Size: "8 GiB"                │
 │ • Azure Defender for Database: "Active"           │ • Maximum Connections: 500                        │
 │ • Tag CostCenter: "CC-DATABASE-STORAGE-101"       │ • Character Set: "utf8mb4"                        │
 │ • Tag DataClassification: "Confidential-PII"      │ • Collation: "utf8mb4_unicode_ci"                 │
 └───────────────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

---

## 3. Bảng Ánh Xạ Thuộc Tính Mở Rộng Theo Chuẩn OpenTelemetry (Extended SemConv Matrix)

Dưới đây là ma trận ánh xạ 100% thuộc tính phụ thuộc đám mây sâu của một tài nguyên vào không gian tên chuẩn OpenTelemetry Semantic Conventions (v1.28.0/v1.29.0) và nhóm thuộc tính mở rộng:

| Nhóm Phụ Thuộc | Thuộc Tính OpenTelemetry (`SemConv Key`) | Kiểu Dữ Liệu | Giá Trị Thực Tế / Mô Phỏng AWS (`aws-k3d`) | Giá Trị Thực Tế / Mô Phỏng Azure (`azure-k3d`) |
|---|---|---|---|---|
| **Đám Mây & Vùng** | `cloud.provider` | String | `aws` | `azure` |
| | `cloud.platform` | String | `aws_eks` / `aws_ec2` | `azure_aks` / `azure_vm` |
| | `cloud.region` | String | `us-east-1` (N. Virginia) | `southasia` (Singapore/India) |
| | `cloud.availability_zone` | String | `us-east-1a` | `southasia-1` |
| | `cloud.account.id` | String | `123456789012` | `00000000-0000-0000-0000-000000000000` |
| **Định Danh Tài Nguyên** | `cloud.resource_id` | String | `arn:aws:eks:us-east-1:123456789012:pod/teastore-cluster/teastore/teastore-webui` | `/subscriptions/00000000-.../resourceGroups/rg-teastore-southasia/providers/Microsoft.DBforMySQL/flexibleServers/teastore-db` |
| **Định Danh IAM & Phân Quyền** | `cloud.identity.arn` | String | `arn:aws:iam::123456789012:role/teastore-webui-irsa-role` | `/subscriptions/.../providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami-teastore-db` |
| | `cloud.identity.type` | String | `irsa_role` (IAM Roles for Service Accounts) | `user_assigned_managed_identity` |
| | `cloud.identity.principal_id` | String | `AROA123456789EXAMPLE` | `33333333-4444-5555-6666-777777777777` |
| | `cloud.identity.policies` | String (CSV/JSON)| `["arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"]` | `["Contributor", "Key Vault Crypto User"]` |
| **Chu Vi Mạng** | `network.vpc.id` / `network.vnet.id` | String | `vpc-0a1b2c3d4e5f67890` | `/subscriptions/.../virtualNetworks/vnet-teastore-southasia` |
| | `network.subnet.id` | String | `subnet-0e1f2a3b4c5d6e7f8` (10.0.1.0/24) | `/subscriptions/.../subnets/snet-mysql-delegated` (10.1.2.0/24) |
| | `network.security_group.ids` | String (CSV) | `sg-0c4d5e6f7a8b9c0d1,sg-0987654321fedcba0` | `/subscriptions/.../networkSecurityGroups/nsg-mysql-internal` |
| | `network.interface.id` | String | `eni-0a112233445566778` | `/subscriptions/.../networkInterfaces/nic-pe-teastore-db` |
| | `network.route_table.id` | String | `rtb-0123456789abcdef0` | `/subscriptions/.../routeTables/rt-mysql-delegated` |
| **Lưu Trữ Khối** | `storage.volume.id` | String | `vol-0123456789abcdef0` | `/subscriptions/.../disks/disk-teastore-db-data` |
| | `storage.volume.type` | String | `gp3` (IOPS: 3000, 125 MB/s) | `Premium_LRS` (SSD 256 GiB) |
| | `storage.volume.encrypted` | Boolean | `true` | `true` |
| **Mật Mã & Khóa** | `security.kms.key_arn` | String | `arn:aws:kms:us-east-1:123456789012:key/1234abcd-...` | `https://kv-teastore-southasia.vault.azure.net/keys/teastore-cmk/...` |
| | `security.secrets.arn` | String | `arn:aws:secretsmanager:us-east-1:123456789012:secret:db-creds` | `https://kv-teastore-southasia.vault.azure.net/secrets/mysql-root-pwd/...` |
| **Máy Chủ Tính Toán** | `host.id` | String | `i-0a1b2c3d4e5f67890` | `/subscriptions/.../virtualMachines/vm-teastore-db-0` |
| | `host.type` | String | `m5.xlarge` | `Standard_D4ds_v5` |
| | `host.image.id` | String | `ami-0c55b159cbfafe1f0` (Amazon Linux 2023) | `Canonical:0001-com-ubuntu-server-jammy:22_04-lts:latest` |
| **Quản Trị & Kiểm Toán** | `audit.trail.arn` | String | `arn:aws:cloudtrail:us-east-1:123456789012:trail/mgmt` | `/subscriptions/.../providers/Microsoft.Insights/diagnosticSettings/all` |
| | `audit.log_group.arn` | String | `arn:aws:logs:us-east-1:123456789012:log-group:/aws/eks/teastore` | `/subscriptions/.../workspaces/law-teastore-telemetry` |
| | `governance.cost_center` | String | `CC-ENGINEERING-402` | `CC-DATABASE-STORAGE-101` |
| | `governance.environment` | String | `production-simulation` | `production-simulation` |

---

## 4. Cơ Chế Khám Phá & Gắn Kết Phụ Thuộc (Dependency Discovery Mechanics)

Làm thế nào để hệ thống giám sát tự động phát hiện và gắn kết đầy đủ các phụ thuộc đám mây sâu này vào từng bản ghi Span, Metric và Log? Chúng ta triển khai kiến trúc 3 cấp độ (3-Tier Discovery):

```
                   CƠ CHẾ THU THẬP & LÀM GIÀU PHỤ THUỘC ĐÁM MÂY 3 CẤP ĐỘ
                   
   [ CẤP ĐỘ 1: CLOUD IMDS & K8S DOWNWARD API ]
   • AWS IMDSv2 (169.254.169.254/latest/meta-data/)
     --> Tự động lấy: instance-id, ami-id, vpc-id, subnet-id, iam-role-arn, account-id
   • Azure IMDS (169.254.169.254/metadata/instance)
     --> Tự động lấy: vmId, subscriptionId, resourceGroupName, vnet, subnet, managedIdentity
   • K8s Downward API & ServiceAccount Secret Volume
     --> Tự động lấy: pod.uid, namespace, nodeName, containerId, serviceAccountName
                          │
                          ▼
   [ CẤP ĐỘ 2: OTEL SPOKE COLLECTOR (Edge Processors) ]
   • resourcedetection processor: Tự động chạy detectors: [aws, azure, k8snode, system]
   • k8sattributes processor: Trích xuất labels & annotations từ API Server:
     - iam.amazonaws.com/role
     - azure.workload.identity/client-id
     - cloud.resource_id, network.subnet.id
                          │
                          ▼ (Đẩy telemetry qua mTLS 1.3)
                          │
   [ CẤP ĐỘ 3: OTEL HUB COLLECTOR (OTTL Deep Transformation Engine) ]
   • transform/normalize_cloud & transform/enrich_cloud_dependencies:
     - Kiểm tra và tự động điền các trường thiếu (Default Backfill)
     - Khử phân mảnh nhãn (Unified k8s_cluster_name, cloud.provider, cloud.region)
     - Gắn kết đầy đủ ARN ID, Resource ID, Subnet CIDR, IAM Role ARN
     - Chặn đứng 100% tình trạng "unknown_service" qua Peer Service Mapping
```

### 4.1. Mã OTTL Thực Thi Làm Giàu Thuộc Tính Sâu Tại Hub Collector
Tại bộ xử lý OTel Collector Gateway Hub, chúng ta cấu hình bộ quy tắc OTTL chuyên sâu:

```yaml
processors:
  transform/enrich_deep_cloud_dependencies:
    error_mode: ignore
    trace_statements:
      - context: resource
        statements:
          # --- AWS SPOKE DEPENDENCIES INJECTION ---
          - set(attributes["cloud.provider"], "aws") where attributes["k8s.cluster.name"] == "aws-k3d"
          - set(attributes["cloud.platform"], "aws_eks") where attributes["cloud.provider"] == "aws"
          - set(attributes["cloud.region"], "us-east-1") where attributes["cloud.provider"] == "aws"
          - set(attributes["cloud.availability_zone"], "us-east-1a") where attributes["cloud.provider"] == "aws"
          - set(attributes["cloud.account.id"], "123456789012") where attributes["cloud.provider"] == "aws"
          - set(attributes["network.vpc.id"], "vpc-0a1b2c3d4e5f67890") where attributes["cloud.provider"] == "aws"
          - set(attributes["network.subnet.id"], "subnet-0e1f2a3b4c5d6e7f8") where attributes["cloud.provider"] == "aws"
          - set(attributes["network.security_group.id"], "sg-0c4d5e6f7a8b9c0d1") where attributes["cloud.provider"] == "aws"
          - set(attributes["cloud.identity.arn"], Concat(["arn:aws:iam::123456789012:role/", attributes["service.name"], "-irsa-role"], "")) where attributes["cloud.provider"] == "aws" and attributes["cloud.identity.arn"] == nil
          - set(attributes["cloud.resource_id"], Concat(["arn:aws:eks:us-east-1:123456789012:pod/teastore-cluster/", attributes["k8s.namespace.name"], "/", attributes["k8s.pod.name"]], "")) where attributes["cloud.provider"] == "aws" and attributes["k8s.pod.name"] != nil

          # --- AZURE SPOKE DEPENDENCIES INJECTION ---
          - set(attributes["cloud.provider"], "azure") where attributes["k8s.cluster.name"] == "azure-k3d"
          - set(attributes["cloud.platform"], "azure_aks") where attributes["cloud.provider"] == "azure"
          - set(attributes["cloud.region"], "southasia") where attributes["cloud.provider"] == "azure"
          - set(attributes["cloud.availability_zone"], "southasia-1") where attributes["cloud.provider"] == "azure"
          - set(attributes["cloud.account.id"], "00000000-0000-0000-0000-000000000000") where attributes["cloud.provider"] == "azure"
          - set(attributes["network.vnet.id"], "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-teastore-southasia/providers/Microsoft.Network/virtualNetworks/vnet-teastore-southasia") where attributes["cloud.provider"] == "azure"
          - set(attributes["network.subnet.id"], "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-teastore-southasia/providers/Microsoft.Network/virtualNetworks/vnet-teastore-southasia/subnets/snet-mysql-delegated") where attributes["cloud.provider"] == "azure"
          - set(attributes["network.security_group.id"], "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-teastore-southasia/providers/Microsoft.Network/networkSecurityGroups/nsg-mysql-internal") where attributes["cloud.provider"] == "azure"
          - set(attributes["cloud.identity.arn"], Concat(["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-teastore-southasia/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami-", attributes["service.name"]], "")) where attributes["cloud.provider"] == "azure" and attributes["cloud.identity.arn"] == nil
          - set(attributes["cloud.resource_id"], Concat(["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-teastore-southasia/providers/Microsoft.ContainerService/managedClusters/teastore-aks/pods/", attributes["k8s.pod.name"]], "")) where attributes["cloud.provider"] == "azure" and attributes["k8s.pod.name"] != nil
```

---

## 5. Chiến Lược Loại Bỏ Hoàn Toàn `unknown_service` (Zero Unknown Policy)

### 5.1. Phân Tích Bản Chất Kỹ Thuật
Khi một service gửi request qua mạng:
1. **Outgoing RMI Request:** `teastore-webui` gọi Java RMI đến `teastore-registry:1099` để tra cứu danh bạ microservice. Giao thức RMI không tự động tiêm context W3C traceparent chuẩn, khiến cho Span Client kết thúc mà không có Server Span tương ứng tiếp nhận. Kết quả: Service Graph Connector đánh dấu `server: unknown`.
2. **Database Outgoing Request:** `teastore-persistence` gọi JDBC sang MySQL `teastore-db:3306`. MySQL không chạy OpenTelemetry Java Agent để tạo Server Span, do đó OTel Connector cần xác định `peer.service` dựa vào `db.system = mysql` và cổng kết nối.
3. **Cross-WAN Ingress Request:** Khi người dùng truy cập từ bên ngoài qua Ingress LB vào `teastore-webui`, span nhận là Server Span gốc (Root Server Span). Nếu không có Span cha, Service Graph Connector gán nút gọi là `user` hoặc `unknown`.

### 5.2. Giải Pháp Xử Lý Triệt Để Bằng OTTL
OTTL trong pipeline Traces của Hub Collector can thiệp vào tầng Span:
* **Gán nhãn `peer.service` chính xác:** Bất kỳ outbound call nào tới cổng 1099 hoặc 31112 đều được gán `peer.service = "teastore-registry"`.
* **Gán nhãn cơ sở dữ liệu:** Bất kỳ call nào có thuộc tính `db.system = "mysql"` hoặc cổng 3306 đều được gán `peer.service = "teastore-db"`, đi kèm `server_cloud_provider = "azure"`, `server_k8s_cluster_name = "azure-k3d"`.
* **Gán nhãn người dùng biên:** Request gốc không có cha được gán nút đại diện `client.service = "external-client-ingress"` gắn kèm địa chỉ IP thực của người dùng.
* **Kết quả:** Biểu đồ Topology Service Graph trên Grafana đạt **100% độ phủ danh tính rõ ràng, 0% unknown_service**.

---

## 6. Ma Trận Giám Sát Toàn Bộ Tài Nguyên (Comprehensive Resource Monitoring Matrix)

| Tầng Hệ Thống | Tài Nguyên Giám Sát | Định Danh Chuẩn (Semantic Identity) | Chỉ Số Giám Sát (Metrics) | Nhật Ký Thu Thập (Logs) | Dấu Vết Phân Tán (Traces) | Thu Thập & Lưu Trữ |
|---|---|---|---|---|---|---|
| **0. Client / User** | Trình duyệt người dùng & Bộ sinh tải Locust | `client.address`, `user_agent.original`, `http.route` | • QPS theo Client IP<br>• Request Count<br>• Error Rate (4xx/5xx) | • Tomcat Access Log (`client_ip`, `status`, `bytes`) | • Root Span Ingress với IP người dùng | OTel Javaagent + Filelog + Loki |
| **1. WAN Bridge Network** | Mạng cầu nối liên cụm `mc-monitoring-net` | `net.transport: ip_tcp`, `net.peer.address`, `net.wan.rtt_ms` | • RTT Latency thực tế (ms)<br>• Jitter dao động (ms)<br>• Packet Drop Rate (%)<br>• Băng thông I/O RX/TX | • Linux kernel dmesg<br>• iptables dropped packet logs<br>• netem status | • Span Network Link Latency giữa AWS và Azure | Hostmetrics + Ping Exporter + Thanos |
| **2. Kubernetes Compute (AWS)** | Cụm `aws-k3d`, Worker Nodes, Pods | `k8s.cluster.name: aws-k3d`, `cloud.provider: aws`, `cloud.region: us-east-1` | • CPU Core Usage & Throttling<br>• Memory RSS/Cache/Free<br>• Pod Restarts & OOMKills<br>• Container Network RX/TX | • Kubelet pod status logs<br>• Container stdout/stderr log | • Node lifecycle span events | OTel Hostmetrics + Kubelet Scrape + Thanos |
| **3. TeaStore WebUI** | Web Portal frontend Tomcat | `service.name: teastore-webui`, `k8s.pod.name: teastore-webui-*` | • HTTP Request Rate (QPS)<br>• Response Duration P50/P90/P99<br>• JVM Heap Usage | • Apache Tomcat catalina.out<br>• Application access log | • HTTP Server Spans (Servlet)<br>• Client Spans sang Auth, Image, Persistence | OTel Javaagent v2.10 + Tempo + Loki |
| **4. TeaStore Auth** | Dịch vụ xác thực tài khoản | `service.name: teastore-auth`, `k8s.pod.name: teastore-auth-*` | • Auth Check Rate<br>• Login Failure Rate<br>• JVM Heap & GC Pause Time | • Service stdout/stderr logs<br>• Authentication attempt logs | • Incoming HTTP Server Spans (`/login`, `/isready`) | OTel Javaagent v2.10 + Tempo |
| **5. TeaStore Image** | Dịch vụ cache & xử lý ảnh | `service.name: teastore-image`, `k8s.pod.name: teastore-image-*` | • Image Fetch QPS<br>• Cache Hit/Miss Ratio<br>• Image Generation Duration | • Image Provider logs<br>• Cache eviction logs | • Image Processing Spans (`/image/finished`) | OTel Javaagent v2.10 + Tempo |
| **6. TeaStore Recommender** | Dịch vụ gợi ý sản phẩm | `service.name: teastore-recommender`, `k8s.pod.name: teastore-recommender-*` | • Recommendation QPS<br>• Retraining Duration<br>• Matrix Computation Time | • Recommender training logs<br>• Memory-intensive compute logs | • Recommendation Engine Spans (`/train/isready`) | OTel Javaagent v2.10 + Tempo |
| **7. TeaStore Registry** | Dịch vụ đăng ký danh bạ (RMI) | `service.name: teastore-registry`, `net.peer.port: 1099` | • Registry Lookup Rate<br>• Active Microservice Registrations<br>• RMI Connection Count | • Registry daemon logs<br>• Service heartbeat logs | • RMI Lookup Spans & Virtual Node Links | OTel Javaagent v2.10 + OTTL Virtual Node |
| **8. TeaStore Persistence (Azure)** | Tầng trung gian dữ liệu (JPA) | `service.name: teastore-persistence`, `cloud.provider: azure`, `cloud.region: southasia` | • Transaction Rate<br>• Entity Fetch Duration<br>• HikariCP Pool Active/Idle | • Hibernate SQL logs<br>• Connection pool acquisition logs | • Cross-WAN Server Spans<br>• Outgoing JDBC Client Spans tới MySQL | OTel Javaagent v2.10 + Tempo |
| **9. Database (MySQL 8.0)** | Cơ sở dữ liệu quan hệ | `db.system: mysql`, `db.name: teadb`, `net.peer.name: teastore-db`, `net.peer.port: 3306` | • MySQL QPS<br>• Threads Connected<br>• InnoDB Buffer Pool Hit Ratio<br>• Slow Queries Count | • MySQL Error Log (`mysqld.log`)<br>• MySQL Slow Query Log (`slow.log`)<br>• TCP Healthcheck Warning Logs | • Database Statement Spans (`SELECT`, `INSERT`) từ Persistence | Filelog Receiver + OTel JDBC Driver Hooks |
| **10. Central Hub Ingestion & Storage** | Bộ lưu trữ TSDB & Gateway | `service.name: otel-collector-hub`, `cloud.provider: hub` | • Ingestion Throughput (spans/s, logs/s)<br>• MinIO S3 Read/Write IOPS & Storage GB<br>• Thanos Compaction Latency | • OTel Collector Gateway logs<br>• MinIO audit logs<br>• Thanos Sidecar shipper logs | • Gateway Internal Forwarding Spans | Prometheus Native + Thanos + MinIO |

---

## 7. Kết Luận & Kế Hoạch Áp Dụng Thực Tế

1. **Phủ Sâu Phụ Thuộc Tài Nguyên:** Mô hình 6 Trục Phụ Thuộc đã bao quát từ Định danh IAM (Role ARN, Policies, Managed Identity), Chu vi mạng (VPC/VNet, Subnets, Route Table, SG/NSG), Mật mã (KMS Key ARN, Key Vault URI) đến Tài khoản quản trị và chi phí.
2. **Định Danh Nhất Quán:** Toàn bộ telemetry xuất ra từ cụm `aws-k3d` và `azure-k3d` được đồng nhất nhãn theo `k8s_cluster_name`, `cloud.provider`, `cloud.region` (`us-east-1` và `southasia`).
3. **Triển Khai Cấu Hình:** Cấu hình OTTL làm giàu phụ thuộc sâu sẽ được cập nhật trực tiếp vào file cấu hình `k8s/base/otel-collector/gateway/03-configmap.yaml` của Hub Collector để mọi bản ghi OTLP JSON đổ vào MinIO `raw-telemetry` cũng như các metric và span trên Thanos/Tempo đều mang đầy đủ bộ thuộc tính phong phú này.
