#!/usr/bin/env bash
# ==============================================================================
# Fault-free (normal) AI training/evaluation data collection for the 4-cluster lab.
#
# Usage:
#   scripts/run_data_collection.sh <run_id> [duration_s] [min_users] [max_users] [--erratic]
#   e.g. scripts/run_data_collection.sh 20261112_teastore_normal-baseline_run02 14400 4 50
#
# Writes experiments/raw/<run_id>/{metrics,workload,system}. Raw files are never
# overwritten: the script refuses to reuse an existing run directory.
# ==============================================================================
set -uo pipefail

RUN_ID="${1:?usage: $0 <run_id> [duration_s] [min_users] [max_users] [--erratic]}"
DURATION="${2:-14400}"
MIN_USERS="${3:-4}"
MAX_USERS="${4:-50}"
ERRATIC="${5:-}"
INTERVAL=10      # must match the detector polling interval used for evaluation
WARMUP=180       # traffic runs this long before sampling so cold JVMs are excluded
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/experiments/raw/${RUN_ID}"
PY="${PYTHON:-python3.12}"   # collector imports torch via the detector feature client

if [[ -e "${OUT}" ]]; then
  echo "Refusing to overwrite existing run directory ${OUT}" >&2
  exit 2
fi
mkdir -p "${OUT}/workload" "${OUT}/metrics" "${OUT}/system"
cp "$0" "${OUT}/system/run_command.sh"
echo "$0 $*" > "${OUT}/system/invocation.txt"
cd "${ROOT}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" | tee -a "${OUT}/system/run.log"; }

# --- Provenance snapshots --------------------------------------------------
{ git rev-parse HEAD; git status --porcelain; } > "${OUT}/system/git_commit.txt"
for node in k3d-aws-k3d-server-0 k3d-azure-k3d-server-0 k3d-gcp-k3d-server-0; do
  echo "${node} $(docker run --rm --net=container:${node} alpine:3.20 sh -c \
    'apk add --no-cache iproute2 >/dev/null 2>&1 && tc qdisc show dev eth0' 2>&1)"
done > "${OUT}/system/netem_start.txt"
for ctx in hub aws azure gcp; do
  kubectl --context "k3d-${ctx}-k3d" get pods -A -o json
done | "${PY}" -c '
import json, sys
rows, decoder, text = [], json.JSONDecoder(), sys.stdin.read()
pos = 0
while pos < len(text.rstrip()):
    doc, pos = decoder.raw_decode(text, pos)
    while pos < len(text) and text[pos].isspace():
        pos += 1
    for pod in doc["items"]:
        statuses = {s["name"]: s for s in pod.get("status", {}).get("containerStatuses", [])}
        for c in pod["spec"]["containers"]:
            s = statuses.get(c["name"], {})
            rows.append({"node": pod["spec"].get("nodeName"), "namespace": pod["metadata"]["namespace"],
                         "pod": pod["metadata"]["name"], "container": c["name"], "image": s.get("image", c["image"]),
                         "image_id": s.get("imageID"), "ready": s.get("ready"), "restarts": s.get("restartCount"),
                         "resources": c.get("resources", {})})
json.dump(rows, sys.stdout, indent=1)
' > "${OUT}/system/pods_snapshot_start.json"

log "run ${RUN_ID} start duration=${DURATION}s interval=${INTERVAL}s users=${MIN_USERS}-${MAX_USERS} ${ERRATIC}"

# --- Prometheus port-forward, restarted and logged on exit -------------------
(
  while true; do
    echo "$(ts) port-forward start" >> "${OUT}/system/port-forward.log"
    kubectl --context k3d-hub-k3d -n monitoring port-forward svc/prometheus 9090:9090 \
      >> "${OUT}/system/port-forward.log" 2>&1
    echo "$(ts) port-forward exited rc=$?" >> "${OUT}/system/port-forward.log"
    sleep 2
  done
) &
PF_LOOP=$!

TRAFFIC=""
cleanup() {
  [[ -n "${TRAFFIC}" ]] && { kill -TERM "${TRAFFIC}" 2>/dev/null; wait "${TRAFFIC}" 2>/dev/null; }
  kill -STOP "${PF_LOOP}" 2>/dev/null
  pkill -P "${PF_LOOP}" 2>/dev/null
  kill -KILL "${PF_LOOP}" 2>/dev/null
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -s -o /dev/null -m 2 http://localhost:9090/-/ready && break
  sleep 1
done
curl -s -o /dev/null -m 2 http://localhost:9090/-/ready || { log "prometheus unreachable"; exit 1; }
curl -s -f -o /dev/null -m 10 http://localhost:8080/tools.descartes.teastore.webui/status \
  || { log "TeaStore entrypoint unreachable"; exit 1; }
log "prometheus and TeaStore reachable"

"${PY}" tests/locust/traffic_generator.py \
  --url "http://localhost:8080/tools.descartes.teastore.webui" \
  --min-users "${MIN_USERS}" --max-users "${MAX_USERS}" --duration "$((DURATION + WARMUP))" \
  ${ERRATIC:+--erratic} > "${OUT}/workload/traffic_generator.log" 2>&1 &
TRAFFIC=$!
log "traffic generator pid=${TRAFFIC}; warm-up ${WARMUP}s before sampling"
sleep "${WARMUP}"

"${PY}" ai-engine/data/collector.py \
  --prometheus-url http://localhost:9090 \
  --duration "${DURATION}" --interval "${INTERVAL}" \
  --output "${OUT}/metrics/entity_features.csv" --label 0 \
  --summary-out "${OUT}/metrics/collection_summary.json" \
  > "${OUT}/system/collector.log" 2>&1
COLLECTOR_RC=$?
log "collector exited rc=${COLLECTOR_RC}"
cleanup
TRAFFIC=""
log "run ${RUN_ID} end"
echo "RUN_DONE ${RUN_ID} collector_rc=${COLLECTOR_RC} rows=$(($(wc -l < "${OUT}/metrics/entity_features.csv") - 1))"
exit "${COLLECTOR_RC}"
