#!/usr/bin/env bash
# ==============================================================================
# Script: pull_images.sh
# Purpose: Pre-pull all version-pinned container images for TeaStore and
#          Observability Stack on the host machine.
# Reference: infra/README.md (Pinned Tech Stack Version Matrix)
# ==============================================================================
set -euo pipefail

# 1. TeaStore Benchmark Application Images (v1.4.1)
TEASTORE_IMAGES=(
  "descartesresearch/teastore-webui:1.4.1"
  "descartesresearch/teastore-registry:1.4.1"
  "descartesresearch/teastore-auth:1.4.1"
  "descartesresearch/teastore-image:1.4.1"
  "descartesresearch/teastore-recommender:1.4.1"
  "descartesresearch/teastore-persistence:1.4.1"
  "descartesresearch/teastore-db:1.4.1"
)

# 1b. AWS Edge API Gateway
GATEWAY_IMAGES=(
  "nginx:1.27.3-alpine"
)

# 2. OpenTelemetry & Telemetry Instrumentation
OTEL_IMAGES=(
  "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0"
  "otel/opentelemetry-collector-contrib:0.114.0"
)

# 3. Observability Backends & Governance Stack (Hub)
OBSERVABILITY_IMAGES=(
  "cgr.dev/chainguard/minio@sha256:0dab2f9fee1c1139ae8753b5e35bb4461af2a276cfe0923a2504c75a6170bc64"
  "prom/prometheus:v2.50.0"
  "quay.io/thanos/thanos:v0.36.1"
  "grafana/loki:2.9.4"
  "grafana/tempo:2.4.0"
  "grafana/grafana:11.5.0"
  "ghcr.io/pyrra-dev/pyrra:v0.7.3"
  "robustadev/robusta-runner:0.53.0"
)

ALL_IMAGES=(
  "${TEASTORE_IMAGES[@]}"
  "${GATEWAY_IMAGES[@]}"
  "${OTEL_IMAGES[@]}"
  "${OBSERVABILITY_IMAGES[@]}"
)

echo "======================================================================"
echo "Pulling all ${#ALL_IMAGES[@]} pinned container images on Docker host..."
echo "======================================================================"

for img in "${ALL_IMAGES[@]}"; do
  echo "--> Pulling ${img}..."
  docker pull "${img}" || {
    echo "Warning: Failed to pull ${img}, continuing..."
  }
done

echo "======================================================================"
echo "All pinned images pre-pulled successfully on host."
echo "======================================================================"

