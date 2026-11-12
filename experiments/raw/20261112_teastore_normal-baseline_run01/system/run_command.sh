#!/usr/bin/env bash
# Normal-baseline training data collection for the 4-cluster TeaStore lab.
# Usage: run_baseline.sh <run_id> <duration_seconds>
set -uo pipefail

RUN_ID="$1"
DURATION="${2:-14400}"
INTERVAL=10
ROOT=/home/tuna/multicloud-monitoring
OUT="${ROOT}/experiments/raw/${RUN_ID}"
mkdir -p "${OUT}/workload" "${OUT}/metrics" "${OUT}/system"
cp "$0" "${OUT}/system/run_command.sh"
cd "${ROOT}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "$(ts) run ${RUN_ID} start duration=${DURATION}s interval=${INTERVAL}s" >> "${OUT}/system/run.log"

# Keep the Prometheus port-forward alive for the whole run; every restart is logged
# so gaps can be matched against collector rows afterwards.
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

until curl -s -o /dev/null -m 2 http://localhost:9090/-/ready; do sleep 1; done
echo "$(ts) prometheus reachable" >> "${OUT}/system/run.log"

python3 tests/locust/traffic_generator.py \
  --url "http://localhost:8080/tools.descartes.teastore.webui" \
  --min-users 10 --max-users 50 --duration "${DURATION}" \
  > "${OUT}/workload/traffic_generator.log" 2>&1 &
TRAFFIC=$!
echo "$(ts) traffic generator pid=${TRAFFIC}" >> "${OUT}/system/run.log"

python3 ai-engine/data/collector.py \
  --prometheus-url http://localhost:9090 \
  --duration "${DURATION}" --interval "${INTERVAL}" \
  --output "${OUT}/metrics/entity_features.csv" --label 0 \
  > "${OUT}/system/collector.log" 2>&1
COLLECTOR_RC=$?
echo "$(ts) collector exited rc=${COLLECTOR_RC}" >> "${OUT}/system/run.log"

kill -TERM "${TRAFFIC}" 2>/dev/null; wait "${TRAFFIC}" 2>/dev/null
kill -STOP "${PF_LOOP}" 2>/dev/null
pkill -P "${PF_LOOP}" 2>/dev/null
kill -KILL "${PF_LOOP}" 2>/dev/null
echo "$(ts) run ${RUN_ID} end" >> "${OUT}/system/run.log"
echo "RUN_DONE ${RUN_ID} collector_rc=${COLLECTOR_RC} rows=$(($(wc -l < "${OUT}/metrics/entity_features.csv") - 1))"
