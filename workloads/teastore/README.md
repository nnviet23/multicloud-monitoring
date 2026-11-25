# Benchmark 1: SPEC Research Group TeaStore

> **Namespace:** `teastore`  
> **Kiến trúc:** Microservices E-Commerce phân tán đa đám mây (Distributed Multi-Cloud TeaStore)  
> **Dự toán Tài nguyên (Memory Footprint):** ~1.2 - 1.5 GB RAM trên toàn hệ thống

---

## 1. Phân Bổ Tô-pô Đa Đám Mây (Multi-Cloud Topology)

- **Cụm AWS Spoke (`aws-k3d` - Compute Tier):**
  - `teastore-registry`: Quản lý danh bạ dịch vụ nội bộ (Port 8080).
  - `teastore-webui`: Giao diện người dùng Web, tiếp nhận truy cập Locust (Port 8080).
  - `teastore-auth`: Dịch vụ xác thực và cấp token phiên làm việc (Port 8080).
  - `teastore-recommender`: Dịch vụ gợi ý sản phẩm dựa trên thuật toán Collaborative Filtering (Port 8080).
  - `teastore-image`: Dịch vụ cung cấp hình ảnh sản phẩm (Port 8080).
- **Cụm Azure Spoke (`azure-k3d` - Data Tier):**
  - `teastore-persistence`: Dịch vụ ORM trung gian truy vấn cơ sở dữ liệu (Port 8080).
  - `teastore-db`: Cơ sở dữ liệu MySQL 8.0 lưu trữ danh mục sản phẩm và đơn hàng (Port 3306).

---

## 2. Tiêm Tự Động Viễn Trắc (Zero-Code OTel Instrumentation)
Mọi dịch vụ Java đều được tiêm `opentelemetry-javaagent:2.10.0` qua initContainer và biến môi trường `CATALINA_OPTS`, tự động đẩy Spans và RED Metrics về `otel-collector-spoke:4317`.
