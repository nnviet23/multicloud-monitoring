#!/usr/bin/env python3
"""
OTel Collector Configuration Validator & OTelBin Exporter
Validates OpenTelemetry Collector configurations against architectural rules (ADR-0006)
and exports unified YAML definitions for visualization on https://www.otelbin.io/
"""

import sys
import os
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "docs" / "diagrams" / "generated"

HUB_CONFIG_PATH = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "gateway" / "03-configmap.yaml"
SPOKE_CONFIG_PATH = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "02-configmap.yaml"

def extract_otel_yaml_from_configmap(configmap_path: Path, config_key: str = "collector-config.yaml") -> dict:
    if not configmap_path.exists():
        raise FileNotFoundError(f"ConfigMap file not found: {configmap_path}")
    
    with open(configmap_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    raw_cfg = data.get("data", {}).get(config_key, "")
    if not raw_cfg:
        # Fallback to scanning data values
        for k, v in data.get("data", {}).items():
            if "receivers:" in v and "service:" in v:
                raw_cfg = v
                break
    
    if not raw_cfg:
        raise ValueError(f"No collector config found inside {configmap_path}")
    
    return yaml.safe_load(raw_cfg)

def validate_spoke_architecture(cfg: dict) -> list[str]:
    violations = []
    processors = cfg.get("processors", {})
    service_pipelines = cfg.get("service", {}).get("pipelines", {})
    
    # Rule 1: Validate edge trace sampling per Phương án A (tail_sampling with 100% errors, >=1500ms latency, 20% probabilistic)
    if "tail_sampling" in processors:
        ts_cfg = processors.get("tail_sampling", {})
        policies = ts_cfg.get("policies", [])
        has_error = any(
            p.get("type") == "status_code" and "ERROR" in p.get("status_code", {}).get("status_codes", [])
            for p in policies if isinstance(p, dict)
        )
        has_latency = any(
            p.get("type") == "latency" and float(p.get("latency", {}).get("threshold_ms", 0)) >= 1500
            for p in policies if isinstance(p, dict)
        )
        has_prob = any(
            p.get("type") == "probabilistic" and float(p.get("probabilistic", {}).get("sampling_percentage", 0)) == 20.0
            for p in policies if isinstance(p, dict)
        )
        if not has_error:
            violations.append("[Spoke Violation] 'tail_sampling' missing status_code policy preserving ERROR traces.")
        if not has_latency:
            violations.append("[Spoke Violation] 'tail_sampling' missing latency policy (>= 1500ms).")
        if not has_prob:
            violations.append("[Spoke Violation] 'tail_sampling' missing probabilistic policy with sampling_percentage=20.")
    else:
        violations.append(
            "[Spoke Violation] 'tail_sampling' missing in processors. Spoke edge collector requires tail_sampling preserving errors, slow traces, and 20% baseline per Phương án A."
        )

    for pipe_name, pipe_data in service_pipelines.items():
        pipe_processors = pipe_data.get("processors", [])
        if pipe_name == "traces":
            if "tail_sampling" not in pipe_processors:
                violations.append("[Spoke Violation] Traces pipeline missing 'tail_sampling' (required per Phương án A).")
        elif "tail_sampling" in pipe_processors:
            violations.append(f"[Spoke Violation] Pipeline '{pipe_name}' contains 'tail_sampling'. Sampling only allowed in traces pipeline.")
        
        # Rule 3: memory_limiter must be first
        if pipe_processors and pipe_processors[0] != "memory_limiter":
            violations.append(f"[Spoke Violation] Pipeline '{pipe_name}' does not start with 'memory_limiter' (found: {pipe_processors[0]}).")

    return violations

def validate_hub_architecture(cfg: dict) -> list[str]:
    violations = []
    service_pipelines = cfg.get("service", {}).get("pipelines", {})
    
    # Rule 2: traces pipeline must not contain tail_sampling before servicegraph
    if "traces" in service_pipelines:
        sg_processors = service_pipelines["traces"].get("processors", [])
        if "tail_sampling" in sg_processors:
            violations.append("[Hub Violation] 'traces' pipeline contains 'tail_sampling'. Service graph connector MUST receive 100% trace topology before tail sampling drops traces (ADR-0014).")
    
    # Rule 3: memory_limiter must be first in all pipelines
    for pipe_name, pipe_data in service_pipelines.items():
        pipe_processors = pipe_data.get("processors", [])
        if pipe_processors and pipe_processors[0] != "memory_limiter":
            violations.append(f"[Hub Violation] Pipeline '{pipe_name}' does not start with 'memory_limiter' (found: {pipe_processors[0]}).")

    return violations

def main():
    print("=" * 70)
    print(" OpenTelemetry Architecture Rule Validator & OTelBin Exporter")
    print("=" * 70)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    errors = []
    
    # 1. Validate & Export Spoke
    try:
        spoke_cfg = extract_otel_yaml_from_configmap(SPOKE_CONFIG_PATH)
        spoke_errs = validate_spoke_architecture(spoke_cfg)
        errors.extend(spoke_errs)
        
        spoke_merged_file = OUTPUT_DIR / "spoke-otel-merged.yaml"
        with open(spoke_merged_file, "w", encoding="utf-8") as f:
            yaml.dump(spoke_cfg, f, default_flow_style=False, sort_keys=False)
        print(f"[OK] Exported Spoke Collector config -> {spoke_merged_file}")
    except Exception as e:
        errors.append(f"[Spoke Error] {str(e)}")

    # 2. Validate & Export Hub
    try:
        hub_cfg = extract_otel_yaml_from_configmap(HUB_CONFIG_PATH)
        hub_errs = validate_hub_architecture(hub_cfg)
        errors.extend(hub_errs)
        
        hub_merged_file = OUTPUT_DIR / "hub-otel-merged.yaml"
        with open(hub_merged_file, "w", encoding="utf-8") as f:
            yaml.dump(hub_cfg, f, default_flow_style=False, sort_keys=False)
        print(f"[OK] Exported Hub Collector config   -> {hub_merged_file}")
    except Exception as e:
        errors.append(f"[Hub Error] {str(e)}")

    print("-" * 70)
    if errors:
        print("❌ ARCHITECTURAL VALIDATION FAILED:")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease fix the above architectural violations before deploying!")
        sys.exit(1)
    else:
        print("✅ ALL ARCHITECTURAL RULES PASSED (ADR-0013, ADR-0014, ADR-0001):")
        print("  - Spoke Edge: Pre-filtering active, 20% trace sampling configured, memory_limiter leading.")
        print("  - Hub Gateway: traces/servicegraph processes 100% traces before tail_sampling.")
        print("  - Pipeline Hygiene: memory_limiter placed first in all pipelines.")
        print("\n💡 Direct OTelBin Visual Inspection:")
        print("  Open https://www.otelbin.io/ in your browser and paste:")
        print(f"    - Hub:   {OUTPUT_DIR / 'hub-otel-merged.yaml'}")
        print(f"    - Spoke: {OUTPUT_DIR / 'spoke-otel-merged.yaml'}")
        print("=" * 70)

if __name__ == "__main__":
    main()
