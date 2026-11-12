import json

file_path = "k8s/base/visualization-grafana/dashboards/k8s-infrastructure.json"

with open(file_path, "r", encoding="utf-8") as f:
    d = json.load(f)

for p in d.get("panels", []):
    pid = p.get("id")
    # 1. CPU Panel (ID 201)
    if pid == 201:
        p["title"] = "CPU Usage (400%)"
        p["fieldConfig"]["defaults"]["unit"] = "percent"
        p["fieldConfig"]["defaults"]["max"] = 400
        p["fieldConfig"]["defaults"]["min"] = 0
        p["fieldConfig"]["defaults"]["thresholds"] = {
            "mode": "absolute",
            "steps": [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 250},
                {"color": "red", "value": 350}
            ]
        }
        for t in p.get("targets", []):
            t["expr"] = 'clamp_max(sum(rate(system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster", state!="idle"}[1m])) * 100, 400)'
            t["legendFormat"] = "CPU Used"

    # 2. Memory Panel (ID 202)
    elif pid == 202:
        p["title"] = "Memory Usage (9.59 GB)"
        p["fieldConfig"]["defaults"]["unit"] = "decgbytes"
        p["fieldConfig"]["defaults"]["max"] = 9.59
        p["fieldConfig"]["defaults"]["min"] = 0
        p["fieldConfig"]["defaults"]["thresholds"] = {
            "mode": "absolute",
            "steps": [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 6.5},
                {"color": "red", "value": 8.5}
            ]
        }
        for t in p.get("targets", []):
            t["expr"] = 'avg(system_memory_usage_bytes{k8s_cluster_name=~"$cluster", state="used"}) / (1024*1024*1024)'
            t["legendFormat"] = "RAM Used"

    # 3. Disk Panel (ID 203)
    elif pid == 203:
        p["title"] = "Disk Space Usage (1007 GB WSL2 VHDX)"
        p["description"] = "Dung lượng ổ đĩa ảo VHDX tự động co giãn tối đa 1007 GB (1 TB) được Docker Desktop/WSL2 cấp phát mặc định cho Linux ext4."
        p["fieldConfig"]["defaults"]["unit"] = "decgbytes"
        p["fieldConfig"]["defaults"]["max"] = 1007
        p["fieldConfig"]["defaults"]["min"] = 0
        p["fieldConfig"]["defaults"]["thresholds"] = {
            "mode": "absolute",
            "steps": [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 700},
                {"color": "red", "value": 900}
            ]
        }
        for t in p.get("targets", []):
            t["expr"] = 'avg(system_filesystem_usage_bytes{k8s_cluster_name=~"$cluster", state="used", device="/dev/sde"}) / (1024*1024*1024)'
            t["legendFormat"] = "Disk Used"

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Updated 3 gauges in k8s-infrastructure.json successfully")

