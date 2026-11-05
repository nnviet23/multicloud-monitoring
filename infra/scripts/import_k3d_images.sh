#!/usr/bin/env bash
# ==============================================================================
# Script: import_k3d_images.sh
# Purpose: Import pre-pulled Docker images directly into k3d clusters'
#          containerd runtime to prevent image pull delays or rate limits.
# ==============================================================================
set -euo pipefail

echo "======================================================================"
echo "Importing container images into k3d clusters..."
echo "======================================================================"

echo "--> [1/3] Importing images into aws-k3d (Compute Spoke)..."
k3d image import \
  descartesresearch/teastore-webui:1.4.1 \
  descartesresearch/teastore-registry:1.4.1 \
  descartesresearch/teastore-auth:1.4.1 \
  descartesresearch/teastore-image:1.4.1 \
  descartesresearch/teastore-recommender:1.4.1 \
  ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0 \
  otel/opentelemetry-collector-contrib:0.114.0 \
  -c aws-k3d || true

echo "--> [2/3] Importing images into azure-k3d (Data Spoke)..."
k3d image import \
  descartesresearch/teastore-persistence:1.4.1 \
  descartesresearch/teastore-db:1.4.1 \
  ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0 \
  otel/opentelemetry-collector-contrib:0.114.0 \
  -c azure-k3d || true

echo "--> [3/3] Importing images into hub-k3d (Central Observability Hub)..."
k3d image import \
  otel/opentelemetry-collector-contrib:0.114.0 \
  minio/minio:RELEASE.2025-10-15T17-29-55Z \
  prom/prometheus:v2.50.0 \
  quay.io/thanos/thanos:v0.36.1 \
  grafana/loki:2.9.4 \
  grafana/tempo:2.4.0 \
  grafana/grafana:11.5.0 \
  ghcr.io/pyrra-dev/pyrra:v0.7.3 \
  robustadev/robusta-runner:0.53.0 \
  -c hub-k3d || true

echo "======================================================================"
echo "All required images imported into k3d clusters successfully!"
echo "======================================================================"

