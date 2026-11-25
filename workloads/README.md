# Deployable Benchmark Workloads Catalog

> **Mô hình Quản trị Benchmark:** Danh mục các bộ kiểm thử hiệu năng và kiến trúc đa đám mây sẵn sàng triển khai (Deployable Benchmark Catalog).
> Toàn bộ các manifest tuân thủ nghiêm ngặt chuẩn **Single Responsibility Principle (SRP - SPEC-0001)** và chính sách kiểm soát tuân thủ **Kyverno (SPEC-0005)**.

---

## 1. Danh Mục Các Bộ Benchmark

| Tên Benchmark | Namespace | Công nghệ Lõi | Trọng tâm Đo kiểm | Cụm Spoke 1 (AWS) | Cụm Spoke 2 (Azure) |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`teastore/`** | `teastore` | Java 11, Spring Boot, MySQL | Microservices RED metrics, JVM Heap, Tracing liên cụm qua WAN | Registry, Auth, WebUI, Recommender, Image | Persistence, MySQL Database |
| **`_template/`** | `bench-*` | Khung mẫu Kustomize SRP | Khung mở rộng cho các workload tùy biến mới | Spoke 1 Resources | Spoke 2 Resources |

---

## 2. Hướng Dẫn Hoán Đổi (Swap) Workload trong GitOps

Để kích hoạt hoặc hoán đổi benchmark trên các cụm, cấu hình trong tệp `kustomization.yaml` của từng cụm:

### Tại Cụm AWS Spoke (`deploy/clusters/aws/kustomization.yaml`):
```yaml
resources:
  - ../../../workloads/teastore/aws-spoke           # Benchmark: TeaStore E-Commerce

  # Platform & Policies (Bất biến)
  - ../../platform/otel-collector/edge
  - ../../platform/sealed-secrets
  - ../../policies
```

### Tại Cụm Azure Spoke (`deploy/clusters/azure/kustomization.yaml`):
```yaml
resources:
  - ../../../workloads/teastore/azure-spoke         # Benchmark: TeaStore Persistence & DB

  # Platform & Policies (Bất biến)
  - ../../platform/otel-collector/edge
  - ../../platform/sealed-secrets
  - ../../policies
```
