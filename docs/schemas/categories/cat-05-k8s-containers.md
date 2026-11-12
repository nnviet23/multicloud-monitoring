# Semantic Conventions: CAT-05 Kubernetes & Container Platform

**Status**: Stable (Core K8s Attributes) / Mixed (Container Metrics)  
**Namespace**: `k8s.*`, `container.*`  
**OTel SemConv Domain**: `docs/resource/k8s.md`, `docs/system/container-metrics.md`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-05` quy định chuẩn ngữ nghĩa cho nền tảng điều phối cụm Kubernetes (Kubernetes Orchestration Platform) và môi trường thực thi bộ chứa (Container Runtime).

Trong kiến trúc đồ án, toàn bộ ứng dụng mẫu TeaStore và các thành phần giám sát đều vận hành trên nền tảng Kubernetes (phân bố trên 3 cụm `hub-k3d`, `aws-k3d`, và `azure-k3d`). `CAT-05` cung cấp hệ thống định danh phân cấp 5 tầng của Kubernetes:
$$\text{Cluster} \longrightarrow \text{Node} \longrightarrow \text{Namespace} \longrightarrow \text{Pod} \longrightarrow \text{Container}$$

Các thuộc tính này đóng vai trò quyết định trong việc:
1. **Triệt tiêu va chạm định danh (Anti-Collision Compound Keys):** Tránh hiện tượng nhầm lẫn dữ liệu khi hai cụm khác nhau đều có Namespace tên là `teastore` và Pod tên là `teastore-webui-...`. Bằng cách ghép cặp `(k8s.cluster.name, k8s.pod.uid)`, mỗi thực thể được định danh duy nhất tuyệt đối.
2. **Khai thác K8s Downward API & Pod Metadata:** Truyền định danh Pod Name, Pod IP, Namespace trực tiếp vào OTel Java Agent và OTel Collector.
3. **Phân tích Cgroup Resource Constraints:** Đo lường giới hạn tài nguyên CPU/Memory của container và hiện tượng CPU throttling do giới hạn CFS (`container.cpu.throttling`).

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `k8s.cluster.name` | `k8s_cluster_name` / `cluster` | Stable | Required [1] | string | Tên định danh của cụm Kubernetes. | `aws-k3d`, `azure-k3d`, `hub-k3d` |
| `k8s.node.name` | `k8s_node_name` / `node` | Stable | Required | string | Tên của nút máy chủ Kubernetes Worker Node. | `k3d-aws-k3d-server-0`, `k3d-azure-k3d-server-0` |
| `k8s.namespace.name` | `k8s_namespace_name` / `namespace` | Stable | Required | string | Tên không gian tên Kubernetes. | `teastore`, `monitoring`, `storage` |
| `k8s.pod.name` | `k8s_pod_name` / `pod` | Stable | Required [2] | string | Tên của Pod Kubernetes (chứa hash ngẫu nhiên của Deployment). | `teastore-webui-77c86546b5-abcde` |
| `k8s.pod.uid` | `k8s_pod_uid` | Stable | Required [1] | string | Mã định danh UUID bất biến của Pod do Kube-Apiserver cấp phát. | `c3d4e5f6-a7b8-4c5d-9e0f-1a2b3c4d5e6f` |
| `k8s.container.name` | `k8s_container_name` / `container` | Stable | Required | string | Tên của container bên trong Pod. | `teastore-webui`, `teastore-db` |
| `container.image.name` | `image_name` | Stable | Recommended | string | Tên của container image (không chứa tag). | `descartesresearch/teastore-webui` |
| `container.image.tag` | `image_tag` | Stable | Required [3] | string | Phiên bản ghim cứng (pinned version tag) của container image. | `1.4.1`, `2.10.0`, `11.5.0` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có mặt trên mọi bản ghi telemetry để làm khóa liên kết (Join Key) và chống va chạm định danh trên Central Hub.
- **[2]:** Được truyền vào container qua Kubernetes Downward API (`spec.containers.env.valueFrom.fieldRef.fieldPath: metadata.name`).
- **[3]:** Tuân thủ nghiêm ngặt quy tắc của đồ án: **Không bao giờ dùng tag `latest`**, 100% container images phải ghim phiên bản cụ thể từ `infra/README.md`.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `container.cpu.time` | `container_cpu_usage_seconds_total` | Counter | `s` | +1 | Tổng thời gian CPU mà container tiêu thụ. Đo **Container CPU Utilization**. |
| `container.cpu.throttling.time` | `container_cpu_cfs_throttled_seconds_total` | Counter | `s` | +1 | Thời gian container bị kernel cgroup bóp nghẹt CPU do vượt giới hạn `limits.cpu`. Đo **Container CPU Saturation**. |
| `container.memory.usage` | `container_memory_working_set_bytes` | Gauge | `By` | +1 | Bộ nhớ RAM thực tế đang dùng của container (Working Set). Đo **Container Memory Utilization**. |
| `container.memory.limit` | `container_spec_memory_limit_bytes` | Gauge | `By` | 0 | Giới hạn bộ nhớ cấu hình trong K8s manifest (`limits.memory`). Dùng để tính toán khoảng đệm trước khi bị `OOMKilled`. |
| `k8s.pod.status.phase` | `kube_pod_status_phase` | Gauge | `1` | 0 | Trạng thái vòng đời của Pod (`Running=1`, `Pending=0`, `Failed=0`). Đo **Pod Availability**. |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuẩn hóa nhãn số nhiều sang số ít (`v1.25.0`):**
   - Theo OTel schema `1.25.0`: Các thuộc tính số nhiều được đổi thành số ít: `k8s.pod.labels` $\rightarrow$ `k8s.pod.label`, `container.labels` $\rightarrow$ `container.label`.
2. **Hợp nhất `cluster` vs `k8s_cluster_name`:**
   - Trong quá trình nâng cấp hệ thống (ghi nhận tại `INC-P3-09`), hệ thống đã hợp nhất toàn bộ các biến và nhãn về duy nhất `k8s_cluster_name` thông qua bộ xử lý OTTL `transform/normalize_cloud` tại Hub Collector, đồng thời gán nhãn tĩnh trong scrape config của Prometheus.
3. **Cơ chế Fallback Trong Đồ Án:**
   - Trên Grafana Dashboards `01. Executive Overview` và `04. Compute & OS Kernel (USE)`, biến dropdown `$cluster` truy vấn:
     `label_values(system_cpu_time_seconds_total, k8s_cluster_name)`
   - Cung cấp danh sách các cụm thực tế `aws-k3d`, `azure-k3d`, `hub-k3d` cho người vận hành.

