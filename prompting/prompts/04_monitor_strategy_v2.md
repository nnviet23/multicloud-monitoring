# HOTFIX PHASE 3.5: SỬA LỖI MERGE MULTI-QUERY TABLES & DUAL Y-AXIS TRONG GRAFANA DASHBOARDS

Hãy thực hiện rà soát và sửa nhanh 3 lỗi hiển thị kỹ thuật (Grafana Schema v39 rendering bugs) trong các tệp JSON vừa nâng cấp tại `k8s/base/visualization-grafana/dashboards/`:

1. **Bổ sung Transformation `merge` và đồng bộ nhãn cho các Multi-Query Table Panels:**
   - Tại **`mc-executive-overview.json` (Panel 7 - Cloud Cluster Fleet Health Matrix)**:
     - Sửa `expr` của các targets `B`, `C`, `D` từ `sum by (k8s_cluster_name)` thành `sum by (k8s_cluster_name, cloud_provider)` để khớp hoàn toàn tập khóa chính với target `A`.
     - Bổ sung thuộc tính `"transformations": [{ "id": "merge", "options": {} }]` vào Panel 7 để Grafana nối `Value #A`, `Value #B`, `Value #C`, `Value #D` thành các cột trên cùng một hàng.
   - Tại **`system-topology.json` (Panel 6 - Cluster Node Resource & Network Health Summary Table)** và **`k8s-infrastructure.json` (Panel 8 - Filesystem Usage & Inode Saturation)**:
     - Bổ sung thuộc tính `"transformations": [{ "id": "merge", "options": {} }]` vào cấu hình của cả 2 panel này.

2. **Tách trục Y kép (Dual Y-Axis) cho các Panel có 2 đại lượng khác đơn vị:**
   - Tại **`k8s-infrastructure.json` (Panel 6 - Disk Throughput & IOPS)** và **`Panel 7 (Disk Latency & Queue Length)`** và **`Panel 9 (Network Throughput & Packet Rates)`**:
     - Thêm `overrides` trong `fieldConfig` sử dụng matcher `byFrameRefID` cho `"options": "B"`, cấu hình `"custom.axisPlacement": "right"` và đặt `"unit"` tương ứng (`iops` cho Panel 6B, `short` cho Panel 7B, `pps` cho Panel 9B).
   - Tại **`red-metrics.json` (Panel 4 - Saturation: Host CPU I/O Wait & Active TCP Connections)**:
     - Đặt default unit là `percent` cho `refId: A`, và thêm `overrides` matcher `byFrameRefID` `"options": "B"` với `"custom.axisPlacement": "right"` và `"unit": "short"`.

3. **Kiểm tra tên metric Page Faults:**
   - Trong `k8s-infrastructure.json` (Panel 5, target B), kiểm tra lại với Thanos Query xem OTel `paging` scraper xuất ra tên metric là `system_paging_faults_total` hay chỉ có `system_paging_operations_total`. Nếu cụm đang chạy, hãy xác thực qua API `:9090` và apply lại ConfigMap Grafana.