# OpenTelemetry Semantic Conventions: 8 Atomic Observability Categories

Tài liệu này đóng vai trò là **Mục Lục & Bảng Ánh Xạ Tổng Thể (Master Index & Mapping Matrix)** giữa 8 Danh mục Ngữ nghĩa Nguyên tử của Đồ án với các Namespaces chính thức trong [OpenTelemetry Semantic Conventions Specification](https://github.com/open-telemetry/semantic-conventions).

---

## 1. Triết Lý Thiết Kế 2 Tầng (Two-Tier Architecture)

Để giải quyết triệt để sự nhập nhằng giữa **"Danh mục thuộc tính nguyên tử"** và **"Hồ sơ giám sát thực thể"**, đồ án phân tách cấu trúc schema thành 2 tầng rõ rệt:

```text
[TẦNG 1: ATOMIC CATEGORIES] (docs/schemas/categories/)
  ├── CAT-01: OS & System Kernel            (system.cpu.*, system.memory.*, system.paging.*)
  ├── CAT-02: Storage & Filesystem          (system.disk.*, system.filesystem.*, s3.*)
  ├── CAT-03: Network & Transport           (system.network.*, network.*, tls.*)
  ├── CAT-04: Cloud Context & Perimeter     (cloud.*, aws.*, azure.*, microsoft.entra.*)
  ├── CAT-05: Kubernetes & Containers       (k8s.*, container.*)
  ├── CAT-06: JVM & Process Runtime         (jvm.*, process.*)
  ├── CAT-07: HTTP & RPC APM                (http.*, rpc.*, service.*)
  └── CAT-08: Database Client & Storage     (db.*)
                             │
                             ▼  (Lắp ghép theo ma trận thành phần)
[TẦNG 2: ENTITY PROFILES] (docs/schemas/profiles/)
  ├── webapp-monitoring-schema.yaml         (CAT-04 + CAT-05 + CAT-06 + CAT-07)
  ├── instance-monitoring-schema.yaml       (CAT-01 + CAT-02 + CAT-03 + CAT-04 + CAT-05)
  ├── database-monitoring-schema.yaml       (CAT-01 + CAT-02 + CAT-04 + CAT-05 + CAT-08)
  └── wan-network-monitoring-schema.yaml    (CAT-03 + CAT-04 + CAT-05 + CAT-07)
```

---

## 2. Bảng Đối Chiếu 8 Categories với OTel SemConv Domain

| Category ID | Tên Danh Mục Chuẩn | OTel Namespaces | Trạng Thái OTel | Tài Liệu Chi Tiết |
| :---: | :--- | :--- | :---: | :--- |
| **`CAT-01`** | **OS & System Kernel** | `system.cpu.*`, `system.memory.*`, `system.paging.*`, `host.*` | Stable / Mixed | [cat-01-os-system.md](cat-01-os-system.md) |
| **`CAT-02`** | **Storage & Filesystem** | `system.disk.*`, `system.filesystem.*`, `s3.*` | Stable / Mixed | [cat-02-storage-filesystem.md](cat-02-storage-filesystem.md) |
| **`CAT-03`** | **Network & Transport** | `system.network.*`, `network.*`, `net.*`, `tls.*` | Stable / Experimental | [cat-03-network-transport.md](cat-03-network-transport.md) |
| **`CAT-04`** | **Cloud Context & Perimeter** | `cloud.*`, `aws.*`, `azure.*`, `microsoft.entra.*` | Stable / Experimental | [cat-04-cloud-context.md](cat-04-cloud-context.md) |
| **`CAT-05`** | **Kubernetes & Containers** | `k8s.cluster.*`, `k8s.node.*`, `k8s.pod.*`, `container.*` | Stable | [cat-05-k8s-containers.md](cat-05-k8s-containers.md) |
| **`CAT-06`** | **JVM & Process Runtime** | `jvm.memory.*`, `jvm.gc.*`, `jvm.thread.*`, `process.*` | Mixed | [cat-06-jvm-runtime.md](cat-06-jvm-runtime.md) |
| **`CAT-07`** | **HTTP & RPC APM** | `http.server.*`, `http.client.*`, `rpc.*`, `service.*` | Stable | [cat-07-http-rpc-apm.md](cat-07-http-rpc-apm.md) |
| **`CAT-08`** | **Database Client & Storage**| `db.system.*`, `db.namespace.*`, `db.query.*`, `db.client.*` | Stable | [cat-08-database-mysql.md](cat-08-database-mysql.md) |

---

## 3. Quy Ước Bảng Định Nghĩa Chuẩn OpenTelemetry Specification

Mỗi tài liệu trong thư mục `categories/` này được cấu trúc theo 4 phần quy chuẩn:
1. **Header & Context:** Định rõ trạng thái tính ổn định (`Stable`, `Mixed`, `Development`), namespace OTel tương ứng và vị trí trong kiến trúc tổng thể.
2. **Attribute Registry Table:** Bảng thuộc tính định danh, kiểu dữ liệu, mức độ bắt buộc (`Required`, `Conditionally Required`, `Recommended`), mô tả và ví dụ thực tế trong đồ án.
3. **Metric & Signal Definitions Table:** Bảng các số đo (Instruments), tên metric xuất ra Prometheus TSDB, loại công cụ (`Counter`, `Gauge`, `Histogram`), đơn vị chuẩn UCUM (`s`, `By`, `{packet}`, `%`), hướng biến thiên (`Orientation: +1/0`) và vai trò trong phương pháp luận USE / RED.
4. **Schema Evolution Notes:** Ghi nhận lịch sử đổi tên chính thức từ OTel `schemas/1.21.0 -> 1.45.0` và cách đồ án hiện thực hóa **Dual SemConv Fallback** để bảo toàn tính tương thích ngược.

