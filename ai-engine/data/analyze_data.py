#!/usr/bin/env python3.12
"""
Exploratory Data Analysis (EDA) for Multi-Cloud Per-Entity Telemetry (V3).
Analyzes per-(cloud_provider, service_name) metrics across AWS, Azure, and GCP,
computes Median / IQR / P95 / P99 baselines, and generates visual plots + markdown report.
"""

import os
import json
import yaml
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description="Multi-Cloud Per-Entity Telemetry EDA (V3)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    raw_csv = cfg["data"]["raw_csv_path"]
    processed_dir = cfg["data"]["processed_dir"]
    features = cfg["data"]["features"]
    os.makedirs(processed_dir, exist_ok=True)

    df = pd.read_csv(raw_csv)
    df["entity"] = df["cloud_provider"] + ":" + df["service_name"]
    entities = sorted(df["entity"].unique())
    cycles = df["cycle_id"].nunique() if "cycle_id" in df.columns else len(df) // max(1, len(entities))

    # Plot 4-panel Multi-Cloud Entity Summary
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(
        f"Multi-Cloud Per-Entity Telemetry Baseline ({len(df)} Entity Samples across {len(entities)} Services on AWS, Azure, GCP)",
        fontsize=13,
        fontweight="bold"
    )

    for ent in entities:
        sub = df[df["entity"] == ent].sort_values("timestamp")
        x = np.arange(len(sub))
        axes[0, 0].plot(x, sub["qps"], label=ent, linewidth=1.2)
        axes[0, 1].plot(x, sub["server_latency_p95"] * 1000.0, label=ent, linewidth=1.2)
        axes[1, 0].plot(x, sub["max_pod_cpu_pct"], label=ent, linewidth=1.2)
        axes[1, 1].plot(x, sub["ram_floor_2m_pct"], label=ent, linewidth=1.2)

    axes[0, 0].set_title("Per-Entity Request Throughput (QPS)")
    axes[0, 0].set_ylabel("Requests / sec")
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend(fontsize=8)

    axes[0, 1].set_title("Per-Entity Server Processing Latency P95 (ms)")
    axes[0, 1].set_ylabel("Latency (ms)")
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].legend(fontsize=8)

    axes[1, 0].set_title("Per-Entity Max Pod CPU Utilization (%)")
    axes[1, 0].set_ylabel("CPU (%)")
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].legend(fontsize=8)

    axes[1, 1].set_title("Per-Entity 2-Minute Rolling RAM Floor (%) [Memory Leak Indicator]")
    axes[1, 1].set_ylabel("2-Min RAM Floor (%)")
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].legend(fontsize=8)

    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    plot_path = os.path.join(processed_dir, "eda_summary.png")
    plt.savefig(plot_path, dpi=150)
    plt.close()

    # Build Markdown Report
    lines = [
        "# Multi-Cloud Per-Entity Telemetry EDA Report (V3)",
        "",
        f"- **Dataset File**: `{raw_csv}`",
        f"- **Total Sampling Cycles**: `{cycles}`",
        f"- **Total Entity Rows**: `{len(df)}`",
        f"- **Discovered Multi-Cloud Entities ({len(entities)})**: {', '.join(f'`{e}`' for e in entities)}",
        "",
        "## Per-Entity Baseline Statistics (Median / IQR / P95 / P99)",
        "",
        "| Entity (`cloud:service`) | QPS Med (P95) | Server Lat P95 Med (P99) | Client Lat P95 Med (P99) | CPU% Med (P95) | RAM% Med (P95) | 2-Min RAM Floor P99 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for ent in entities:
        sub = df[df["entity"] == ent]
        qps_m, qps_95 = np.percentile(sub["qps"], [50, 95])
        sl_m, sl_99 = np.percentile(sub["server_latency_p95"] * 1000.0, [50, 99])
        cl_m, cl_99 = np.percentile(sub["client_latency_p95"] * 1000.0, [50, 99])
        cpu_m, cpu_95 = np.percentile(sub["max_pod_cpu_pct"], [50, 95])
        ram_m, ram_95 = np.percentile(sub["max_pod_ram_pct"], [50, 95])
        flr_99 = np.percentile(sub["ram_floor_2m_pct"], 99)
        lines.append(
            f"| `{ent}` | {qps_m:.1f} ({qps_95:.1f}) | {sl_m:.1f}ms ({sl_99:.1f}ms) | "
            f"{cl_m:.1f}ms ({cl_99:.1f}ms) | {cpu_m:.1f}% ({cpu_95:.1f}%) | "
            f"{ram_m:.1f}% ({ram_95:.1f}%) | {flr_99:.1f}% |"
        )

    lines.extend([
        "",
        "## Visual Summary",
        "",
        "![Multi-Cloud Per-Entity EDA Summary](eda_summary.png)",
        ""
    ])

    report_path = os.path.join(processed_dir, "eda_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[EDA] Saved summary plot to {plot_path} and report to {report_path}", flush=True)


if __name__ == "__main__":
    main()
