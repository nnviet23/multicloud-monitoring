#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-latest}"
IMAGE="measurement:${TAG}"

docker build -t "${IMAGE}" .
k3d image import "${IMAGE}" -c aws-k3d
k3d image import "${IMAGE}" -c azure-k3d
printf 'Imported %s into aws-k3d and azure-k3d\n' "${IMAGE}"
