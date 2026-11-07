# Multi-Cloud Observability Resource Schemas

Thư mục này chứa toàn bộ các đặc tả thiết kế, từ điển dữ liệu (Data Dictionary), và tệp cấu hình Schema máy đọc được (Machine-Readable Schemas) làm chuẩn kiểm thử và đánh giá cho toàn bộ dự án Multi-Cloud Monitoring Platform.

## 1. Danh Mục Tài Liệu

- **[RESOURCE_MONITORING_SCHEMAS.md](RESOURCE_MONITORING_SCHEMAS.md):**  
  Tài liệu đặc tả toàn diện kiến trúc 3 Tầng Phụ Thuộc (Application, System, Cloud Dependencies), Từ điển dữ liệu Four Golden Signals & USE Method, Hợp đồng SLI/SLO và Cây chẩn đoán RCA liên tầng (Cross-Layer RCA Correlation Tree).
- **[webapp-monitoring-schema.yaml](webapp-monitoring-schema.yaml):**  
  Đặc tả Schema YAML chuẩn cho các ứng dụng web / microservices (áp dụng cho TeaStore Java/Tomcat Microservices).
- **[instance-monitoring-schema.yaml](instance-monitoring-schema.yaml):**  
  Đặc tả Schema YAML chuẩn cho các nút máy chủ tính toán (Kubernetes Worker Nodes & Cloud VMs theo phương pháp USE).
- **[experiment-manifest.example.yaml](experiment-manifest.example.yaml):**  
  Mẫu manifest định nghĩa một lượt thử nghiệm benchmark (Workload Scenario, Clusters, Network Impairment).
- **[telemetry-field-inventory.example.csv](telemetry-field-inventory.example.csv):**  
  Mẫu danh mục trường dữ liệu đo kiểm (Telemetry Field Inventory).

## 2. Quy Chuẩn Sử Dụng Cho Phase 4 Benchmark
Toàn bộ các bài kiểm thử hiệu năng và đánh giá độ phủ (Coverage Evaluation) trong Phase 4 sẽ đối chiếu trực tiếp với các định nghĩa và câu lệnh truy vấn chuẩn tắc trong thư mục này.

