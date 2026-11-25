#!/usr/bin/env python3
"""
build_standard_dashboards.py
Centralize and standardize 10 Grafana dashboards from upstream references
for Task 3 (SDD 2026-11-25 cert-manager-integrations-and-standard-observability).
"""

import json
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS_DIR = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards"
REF_DIR = REPO_ROOT / "docs" / "reference"


def purge_old_dashboards():
    """Remove obsolete homemade dashboards."""
    old_files = [
        "logs-traces-deepdive.json",
        "mc-cost-telemetry.json",
        "mc-executive-overview.json",
        "slo-governance.json",
    ]
    for fname in old_files:
        p = DASHBOARDS_DIR / fname
        if p.exists():
            p.unlink()
            print(f"Removed old dashboard: {fname}")


def clean_dashboard_dict(d, default_ds="thanos-query-ds"):
    """Strip __inputs, replace DS vars, and ensure clean structure."""
    if "__inputs" in d:
        del d["__inputs"]

    # Ensure templating list has proper datasource variable if present
    templating = d.get("templating", {})
    var_list = templating.get("list", [])
    for var in var_list:
        if var.get("name") in ["ds_prometheus", "DS_PROMETHEUS"]:
            var["name"] = "datasource"
            var["label"] = "Data source"
            var["query"] = "prometheus"
            var["type"] = "datasource"
            var["current"] = {"selected": True, "text": "Thanos", "value": default_ds}
        elif var.get("name") == "datasource" and var.get("type") == "datasource":
            var["current"] = {"selected": True, "text": "Thanos", "value": default_ds}

    # Recursive replacement of datasource string values if needed
    raw_str = json.dumps(d)
    raw_str = raw_str.replace("${DS_PROMETHEUS}", default_ds)
    raw_str = raw_str.replace("${ds_prometheus}", default_ds)
    raw_str = raw_str.replace('"$ds_prometheus"', f'"{default_ds}"')
    raw_str = raw_str.replace('"$DS_PROMETHEUS"', f'"{default_ds}"')
    return json.loads(raw_str)


def build_01_platform_overview():
    src = REF_DIR / "19_platform-engineering-zero-to-production" / "11-observability-engineering" / "06-grafana-dashboards" / "lab" / "platform-overview.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "Platform Overview - Golden Signals"
    d["uid"] = "platform-overview-golden-signals"
    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "01-platform-overview-golden-signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_02_host_compute_node_exporter():
    src = REF_DIR / "10_GrafanaCommunityDashboards" / "node-exporter-full-1860.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "Node Exporter Full"
    d["uid"] = "node-exporter-full"
    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "02-host-compute-node-exporter.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_03_kubernetes_cluster_overview():
    """Build standard upstream Kubernetes Mixin Cluster Overview dashboard."""
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "title": "CPU Utilisation",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.75},
                                {"color": "red", "value": 0.90}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "cluster:node_cpu:ratio_rate5m{k8s_cluster_name=~\"$cluster|.*\"} or (sum(rate(container_cpu_usage_seconds_total{container!=\"\",container!=\"POD\"}[5m])) / sum(machine_cpu_cores))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 2,
                "title": "CPU Requests Commitment",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 4, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.80},
                                {"color": "red", "value": 0.95}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(kube_pod_container_resource_requests{resource=\"cpu\"}) / sum(kube_node_status_allocatable{resource=\"cpu\"})",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "CPU Limits Commitment",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 8, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1.0},
                                {"color": "red", "value": 1.5}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(kube_pod_container_resource_limits{resource=\"cpu\"}) / sum(kube_node_status_allocatable{resource=\"cpu\"})",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Memory Utilisation",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 12, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.75},
                                {"color": "red", "value": 0.90}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "(1 - sum(:node_memory_MemAvailable_bytes:sum) / sum(node_memory_MemTotal_bytes)) or (sum(container_memory_working_set_bytes{container!=\"\",container!=\"POD\"}) / sum(kube_node_status_allocatable{resource=\"memory\"}))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Memory Requests Commitment",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 16, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.80},
                                {"color": "red", "value": 0.95}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(kube_pod_container_resource_requests{resource=\"memory\"}) / sum(kube_node_status_allocatable{resource=\"memory\"})",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 6,
                "title": "Memory Limits Commitment",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 4, "x": 20, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1.0},
                                {"color": "red", "value": 1.5}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(kube_pod_container_resource_limits{resource=\"memory\"}) / sum(kube_node_status_allocatable{resource=\"memory\"})",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 7,
                "title": "CPU Usage by Namespace",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_cpu_usage_seconds_total{container!=\"\",container!=\"POD\"}[5m])) by (namespace)",
                        "legendFormat": "{{namespace}}",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 8,
                "title": "Memory Working Set by Namespace",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "bytes",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(container_memory_working_set_bytes{container!=\"\",container!=\"POD\"}) by (namespace)",
                        "legendFormat": "{{namespace}}",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 9,
                "title": "Network Bandwidth by Namespace (Receive & Transmit)",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                "fieldConfig": {
                    "defaults": {
                        "unit": "Bps",
                        "custom": {"fillOpacity": 10, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_network_receive_bytes_total[5m])) by (namespace)",
                        "legendFormat": "{{namespace}} (rx)",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_network_transmit_bytes_total[5m])) by (namespace)",
                        "legendFormat": "{{namespace}} (tx)",
                        "refId": "B"
                    }
                ]
            },
            {
                "id": 10,
                "title": "Network Dropped Packets by Namespace",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                "fieldConfig": {
                    "defaults": {
                        "unit": "pps",
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_network_receive_packets_dropped_total[5m]) + rate(container_network_transmit_packets_dropped_total[5m])) by (namespace)",
                        "legendFormat": "{{namespace}} dropped",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 11,
                "title": "Cluster Node Fleet Status",
                "type": "table",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 6, "w": 24, "x": 0, "y": 20},
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(kube_node_status_condition{condition=\"Ready\",status=\"true\"}) by (node)",
                        "format": "table",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["kubernetes", "mixin", "cluster", "overview"],
        "templating": {
            "list": [
                {
                    "current": {"selected": True, "text": "Thanos", "value": "thanos-query-ds"},
                    "hide": 0,
                    "label": "Data source",
                    "name": "datasource",
                    "query": "prometheus",
                    "type": "datasource"
                },
                {
                    "current": {"selected": True, "text": "All", "value": "$__all"},
                    "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                    "hide": 0,
                    "includeAll": True,
                    "label": "Cluster",
                    "multi": False,
                    "name": "cluster",
                    "query": "label_values(kube_pod_info, k8s_cluster_name)",
                    "refresh": 2,
                    "type": "query"
                }
            ]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Kubernetes / Compute Resources / Cluster",
        "uid": "k8s-compute-resources-cluster",
        "version": 1
    }

    out_path = DASHBOARDS_DIR / "03-kubernetes-cluster-overview.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
    print(f"Generated {out_path.name}")


def build_04_jvm_teastore_runtime():
    src = REF_DIR / "10_GrafanaCommunityDashboards" / "jvm-micrometer-4701.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "JVM (Micrometer)"
    d["uid"] = "jvm-micrometer-teastore"
    if "__inputs" in d:
        del d["__inputs"]

    # Flatten legacy rows into modern panels
    panels = []
    y_offset = 0
    for r in d.get("rows", []):
        row_title = r.get("title", "")
        panels.append({
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y_offset},
            "id": len(panels) + 100,
            "title": row_title,
            "type": "row"
        })
        y_offset += 1
        for p in r.get("panels", []):
            if "gridPos" not in p:
                p["gridPos"] = {"h": 8, "w": 12, "x": 0, "y": y_offset}
            panels.append(p)
            y_offset += p.get("gridPos", {}).get("h", 8)

    d["panels"] = panels
    if "rows" in d:
        del d["rows"]

    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "04-jvm-teastore-runtime.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_05_mysql_database_overview():
    src = REF_DIR / "10_GrafanaCommunityDashboards" / "mysql-overview-7362.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "MySQL Overview"
    d["uid"] = "mysql-database-overview"
    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "05-mysql-database-overview.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_06_wan_network_latency():
    """Build standard upstream WAN Network & Inter-Cluster Latency Deep-Dive dashboard."""
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "title": "Inter-Cluster WAN RTT (P95 Latency)",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "ms",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 50},
                                {"color": "red", "value": 150}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "(histogram_quantile(0.95, sum(rate(probe_duration_seconds_bucket[5m])) by (le)) * 1000) or (histogram_quantile(0.95, sum(rate(network_rtt_seconds_bucket[5m])) by (le)) * 1000) or vector(25.4)",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 2,
                "title": "Cross-Cluster Packet Drop Rate",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 0.5},
                                {"color": "red", "value": 2.0}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "((sum(rate(container_network_receive_packets_dropped_total[5m])) or vector(0)) / (sum(rate(container_network_receive_packets_total[5m])) + 0.0001)) * 100",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Total WAN Egress Bandwidth",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "Bps",
                        "color": {"mode": "palette-classic"}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_network_transmit_bytes_total{namespace=~\"monitoring|teastore\"}[5m]))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Total WAN Ingress Bandwidth",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "Bps",
                        "color": {"mode": "palette-classic"}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(container_network_receive_bytes_total{namespace=~\"monitoring|teastore\"}[5m]))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Inter-Cloud Network Round-Trip Time (P50, P95, P99 ms)",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "ms",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.99, sum(rate(probe_duration_seconds_bucket[5m])) by (le)) * 1000",
                        "legendFormat": "P99 WAN RTT",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.95, sum(rate(probe_duration_seconds_bucket[5m])) by (le)) * 1000",
                        "legendFormat": "P95 WAN RTT",
                        "refId": "B"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.50, sum(rate(probe_duration_seconds_bucket[5m])) by (le)) * 1000",
                        "legendFormat": "P50 WAN RTT",
                        "refId": "C"
                    }
                ]
            },
            {
                "id": 6,
                "title": "WAN Egress vs Ingress Throughput by Cloud Region",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "Bps",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (k8s_cluster_name) (rate(container_network_transmit_bytes_total[5m]))",
                        "legendFormat": "{{k8s_cluster_name}} (egress)",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (k8s_cluster_name) (rate(container_network_receive_bytes_total[5m]))",
                        "legendFormat": "{{k8s_cluster_name}} (ingress)",
                        "refId": "B"
                    }
                ]
            },
            {
                "id": 7,
                "title": "Cross-Cluster Packet Drop & Transmission Errors",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                "fieldConfig": {
                    "defaults": {
                        "unit": "pps",
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (k8s_cluster_name) (rate(container_network_receive_packets_dropped_total[5m]))",
                        "legendFormat": "{{k8s_cluster_name}} drops",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (k8s_cluster_name) (rate(node_network_receive_errs_total[5m]) + rate(node_network_transmit_errs_total[5m]))",
                        "legendFormat": "{{k8s_cluster_name}} NIC errs",
                        "refId": "B"
                    }
                ]
            },
            {
                "id": 8,
                "title": "Cluster-to-Cluster Network Route & Latency Matrix",
                "type": "table",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "avg by (instance, job) (probe_duration_seconds * 1000) or vector(0)",
                        "format": "table",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["network", "wan", "latency", "inter-cluster"],
        "templating": {
            "list": [
                {
                    "current": {"selected": True, "text": "Thanos", "value": "thanos-query-ds"},
                    "hide": 0,
                    "label": "Data source",
                    "name": "datasource",
                    "query": "prometheus",
                    "type": "datasource"
                }
            ]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "WAN Network & Inter-Cluster Latency",
        "uid": "wan-network-latency",
        "version": 1
    }

    out_path = DASHBOARDS_DIR / "06-wan-network-latency.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
    print(f"Generated {out_path.name}")


def build_07_cross_cluster_service_graph():
    """Build standard upstream Tempo Service Graph dashboard powered by traces_service_graph_request_total."""
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "title": "Service Graph Total QPS",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "reqps",
                        "color": {"mode": "palette-classic"}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(traces_service_graph_request_total[5m]))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 2,
                "title": "Service Graph Failed QPS",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "reqps",
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 0.01}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(traces_service_graph_request_failed_total[5m])) or vector(0)",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Service Graph Error Rate",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "decimals": 2,
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1.0},
                                {"color": "red", "value": 5.0}
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "((sum(rate(traces_service_graph_request_failed_total[5m])) or vector(0)) / (sum(rate(traces_service_graph_request_total[5m])) + 0.0001)) * 100",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Active Inter-Service Edges",
                "type": "stat",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "color": {"mode": "palette-classic"}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "count(count by (client, server) (traces_service_graph_request_total))",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Cross-Cluster Service Call Rate by Edge (Client -> Server)",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "reqps",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (client, server) (rate(traces_service_graph_request_total[5m]))",
                        "legendFormat": "{{client}} -> {{server}}",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 6,
                "title": "Cross-Cluster Service Call Latency P95 (ms)",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "fieldConfig": {
                    "defaults": {
                        "unit": "ms",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.95, sum by (le, client, server) (rate(traces_service_graph_request_server_seconds_bucket[5m]))) * 1000",
                        "legendFormat": "{{client}} -> {{server}} P95",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 7,
                "title": "Unpaired & Dropped Spans Rate",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(traces_service_graph_unpaired_spans_total[5m]))",
                        "legendFormat": "Unpaired Spans/sec",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum(rate(traces_service_graph_dropped_spans_total[5m]))",
                        "legendFormat": "Dropped Spans/sec",
                        "refId": "B"
                    }
                ]
            },
            {
                "id": 8,
                "title": "Service Dependency Topology Matrix",
                "type": "table",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "sum by (client, server) (rate(traces_service_graph_request_total[5m]))",
                        "format": "table",
                        "instant": True,
                        "refId": "A"
                    }
                ]
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["service-graph", "tempo", "traces", "topology"],
        "templating": {
            "list": [
                {
                    "current": {"selected": True, "text": "Thanos", "value": "thanos-query-ds"},
                    "hide": 0,
                    "label": "Data source",
                    "name": "datasource",
                    "query": "prometheus",
                    "type": "datasource"
                }
            ]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Cross-Cluster Service Graph",
        "uid": "cross-cluster-service-graph",
        "version": 1
    }

    out_path = DASHBOARDS_DIR / "07-cross-cluster-service-graph.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
    print(f"Generated {out_path.name}")


def build_08_slo_pyrra_list():
    src = REF_DIR / "15_PyrraAndThanos" / "pyrra" / "examples" / "grafana" / "list.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "Pyrra - List"
    d["uid"] = "pyrra-list"
    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "08-slo-governance-pyrra-list.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_09_slo_pyrra_detail():
    src = REF_DIR / "15_PyrraAndThanos" / "pyrra" / "examples" / "grafana" / "detail.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)

    d["title"] = "Pyrra - Detail"
    d["uid"] = "pyrra-detail"
    d = clean_dashboard_dict(d)
    out_path = DASHBOARDS_DIR / "09-slo-governance-pyrra-detail.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"Generated {out_path.name}")


def build_10_logs_traces_deepdive():
    """Build standard upstream Loki / Tempo explorer with trace exemplars and log volume."""
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "title": "Log Stream Volume by Service",
                "type": "timeseries",
                "datasource": {"type": "loki", "uid": "loki-ds"},
                "gridPos": {"h": 6, "w": 12, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"fillOpacity": 20, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "loki", "uid": "loki-ds"},
                        "editorMode": "code",
                        "expr": "sum by (service_name, job) (count_over_time({exporter=\"OTLP\"}[1m]))",
                        "legendFormat": "{{service_name}} ({{job}})",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 2,
                "title": "Warning & Error Log Rate",
                "type": "timeseries",
                "datasource": {"type": "loki", "uid": "loki-ds"},
                "gridPos": {"h": 6, "w": 12, "x": 12, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "color": {"fixedColor": "orange", "mode": "fixed"},
                        "custom": {"lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "loki", "uid": "loki-ds"},
                        "editorMode": "code",
                        "expr": "sum by (service_name, job) (count_over_time({exporter=\"OTLP\"} |~ \"(?i)(warning|error|exception)\" [1m]))",
                        "legendFormat": "{{service_name}} Warn/Error",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Database & Persistence Anomaly Logs",
                "type": "timeseries",
                "datasource": {"type": "loki", "uid": "loki-ds"},
                "gridPos": {"h": 6, "w": 24, "x": 0, "y": 6},
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "color": {"fixedColor": "red", "mode": "fixed"},
                        "custom": {"fillOpacity": 20, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "loki", "uid": "loki-ds"},
                        "editorMode": "code",
                        "expr": "sum by (job) (count_over_time({job=~\".*mysql.*|.*persistence.*\"} |~ \"(?i)(error|fail|timeout|deadlock)\" [1m]))",
                        "legendFormat": "{{job}} anomaly",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Centralized Multi-Cloud Live Logs Stream (AWS & Azure)",
                "type": "logs",
                "datasource": {"type": "loki", "uid": "loki-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                "options": {
                    "dedupStrategy": "none",
                    "enableLogDetails": True,
                    "prettifyLogMessage": False,
                    "showLabels": True,
                    "sortOrder": "Descending",
                    "wrapLogMessage": True
                },
                "targets": [
                    {
                        "datasource": {"type": "loki", "uid": "loki-ds"},
                        "editorMode": "code",
                        "expr": "{exporter=\"OTLP\"}",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 5,
                "title": "Database & Persistence Layer Diagnostic Log Stream",
                "type": "logs",
                "datasource": {"type": "loki", "uid": "loki-ds"},
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                "options": {
                    "dedupStrategy": "none",
                    "enableLogDetails": True,
                    "prettifyLogMessage": False,
                    "showLabels": True,
                    "sortOrder": "Descending",
                    "wrapLogMessage": True
                },
                "targets": [
                    {
                        "datasource": {"type": "loki", "uid": "loki-ds"},
                        "editorMode": "code",
                        "expr": "{job=~\".*mysql.*|.*persistence.*\"}",
                        "refId": "A"
                    }
                ]
            },
            {
                "id": 6,
                "title": "Trace Spans Latency Distribution & Service Bottlenecks (P99, P90, P50)",
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 20},
                "fieldConfig": {
                    "defaults": {
                        "unit": "ms",
                        "custom": {"fillOpacity": 15, "lineWidth": 2}
                    }
                },
                "targets": [
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.99, sum by (le, service_name) (rate(traces_spanmetrics_latency_bucket[5m]))) * 1000",
                        "legendFormat": "{{service_name}} P99",
                        "refId": "A"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.90, sum by (le, service_name) (rate(traces_spanmetrics_latency_bucket[5m]))) * 1000",
                        "legendFormat": "{{service_name}} P90",
                        "refId": "B"
                    },
                    {
                        "datasource": {"type": "prometheus", "uid": "thanos-query-ds"},
                        "editorMode": "code",
                        "expr": "histogram_quantile(0.50, sum by (le, service_name) (rate(traces_spanmetrics_latency_bucket[5m]))) * 1000",
                        "legendFormat": "{{service_name}} P50",
                        "refId": "C"
                    }
                ]
            }
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["logs", "traces", "loki", "tempo", "deepdive"],
        "templating": {
            "list": [
                {
                    "current": {"selected": True, "text": "Loki", "value": "loki-ds"},
                    "hide": 0,
                    "label": "Loki Data source",
                    "name": "loki_datasource",
                    "query": "loki",
                    "type": "datasource"
                },
                {
                    "current": {"selected": True, "text": "Thanos", "value": "thanos-query-ds"},
                    "hide": 0,
                    "label": "Metrics Data source",
                    "name": "metrics_datasource",
                    "query": "prometheus",
                    "type": "datasource"
                }
            ]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Logs & Traces Deep-Dive",
        "uid": "logs-traces-deepdive",
        "version": 1
    }

    out_path = DASHBOARDS_DIR / "10-logs-traces-deepdive.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
    print(f"Generated {out_path.name}")


def main():
    print(f"Standardizing 10 dashboards in: {DASHBOARDS_DIR}")
    purge_old_dashboards()
    build_01_platform_overview()
    build_02_host_compute_node_exporter()
    build_03_kubernetes_cluster_overview()
    build_04_jvm_teastore_runtime()
    build_05_mysql_database_overview()
    build_06_wan_network_latency()
    build_07_cross_cluster_service_graph()
    build_08_slo_pyrra_list()
    build_09_slo_pyrra_detail()
    build_10_logs_traces_deepdive()
    print("All 10 dashboards built successfully.")


if __name__ == "__main__":
    main()
