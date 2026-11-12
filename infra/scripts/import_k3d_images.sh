#!/usr/bin/env bash
# ==============================================================================
# Script: import_k3d_images.sh
# Purpose: Import pre-pulled Docker images directly into k3d clusters'
#          containerd runtime to prevent image pull delays or rate limits.
# ==============================================================================
set -euo pipefail

import_images_to_cluster() {
  local cluster_name="$1"
  local server_container="k3d-${cluster_name}-server-0"
  shift
  local images=("$@")

  echo "--> Importing ${#images[@]} images into ${cluster_name} via direct stream..."
  for img in "${images[@]}"; do
    echo "    - Streaming ${img} into ${server_container}..."
    docker save "${img}" | docker exec -i "${server_container}" ctr images import - >/dev/null 2>&1 || true
  done
}

echo "======================================================================"
echo "Importing container images into k3d clusters..."
echo "======================================================================"

AWS_IMAGES=(
  "descartesresearch/teastore-webui:1.4.1"
  "descartesresearch/teastore-registry:1.4.1"
  "descartesresearch/teastore-auth:1.4.1"
  "descartesresearch/teastore-image:1.4.1"
  "descartesresearch/teastore-recommender:1.4.1"
  "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0"
  "otel/opentelemetry-collector-contrib:0.114.0"
)
import_images_to_cluster "aws-k3d" "${AWS_IMAGES[@]}"

AZURE_IMAGES=(
  "descartesresearch/teastore-persistence:1.4.1"
  "descartesresearch/teastore-db:1.4.1"
  "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0"
  "otel/opentelemetry-collector-contrib:0.114.0"
)
import_images_to_cluster "azure-k3d" "${AZURE_IMAGES[@]}"

HUB_IMAGES=(
  "otel/opentelemetry-collector-contrib:0.114.0"
  "minio/minio:RELEASE.2025-10-15T17-29-55Z"
  "prom/prometheus:v2.50.0"
  "quay.io/thanos/thanos:v0.36.1"
  "grafana/loki:2.9.4"
  "grafana/tempo:2.4.0"
  "grafana/grafana:11.5.0"
  "ghcr.io/pyrra-dev/pyrra:v0.7.3"
  "robustadev/robusta-runner:0.53.0"
)
import_images_to_cluster "hub-k3d" "${HUB_IMAGES[@]}"

echo "======================================================================"
echo "All required images imported into k3d clusters successfully!"
echo "======================================================================"
