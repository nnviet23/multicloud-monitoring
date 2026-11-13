#!/usr/bin/env bash
# ==============================================================================
# Real fault-injection campaign on the 4-cluster lab with the deployed AI model.
#
# Usage: scripts/run_fault_campaign.sh <experiment_id> [users]
#   e.g. scripts/run_fault_campaign.sh 20261113_teastore_fault-campaign_run01 12
#
# Runs, in order, one shared detector per runner:
#   1. tests/chaos/run_live.py           gcp/azure/aws WAN delay (baseline netem restored)
#   2. tests/chaos/run_service_faults.py cpu, db_lock, memory_leak, http_5xx, webui_outage
# Outputs: experiments/raw/<experiment_id>/{wan,service,system}. Each runner keeps
# detector.json (with per-entity model inputs), events.json and report.json.
# Optional env overrides (an empty value skips that stage):
#   WAN_SCENARIOS="gcp_wan_delay azure_wan_delay aws_wan_delay"
#   SERVICE_SCENARIOS="cpu db_lock memory_leak http_5xx webui_outage"
# memory_leak always runs >= 180s (see MIN_FAULT_SECONDS in run_service_faults.py).
# ==============================================================================
set -uo pipefail

RUN_ID="${1:?usage: $0 <experiment_id> [users]}"
USERS="${2:-12}"
WAN_SCENARIOS="${WAN_SCENARIOS-gcp_wan_delay azure_wan_delay aws_wan_delay}"
SERVICE_SCENARIOS="${SERVICE_SCENARIOS-cpu db_lock memory_leak http_5xx webui_outage}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="experiments/raw/${RUN_ID}"
PY="${PYTHON:-python3.12}"
cd "${ROOT}" || exit 1
if [[ -e "${OUT}" ]]; then
  echo "Refusing to overwrite existing run directory ${OUT}" >&2
  exit 2
fi
mkdir -p "${OUT}/system"
cp "$0" "${OUT}/system/run_command.sh"
{ git rev-parse HEAD; git status --porcelain; } > "${OUT}/system/git_commit.txt"
sha256sum ai-engine/models/saved/*.pt ai-engine/models/saved/*.json > "${OUT}/system/model_sha256.txt"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" | tee -a "${OUT}/system/run.log"; }

# Prometheus/Tempo port-forwards are spawned by the detector itself when absent.
log "campaign ${RUN_ID} start users=${USERS} wan=[${WAN_SCENARIOS}] service=[${SERVICE_SCENARIOS}]"
WAN_RC=skipped
if [[ -n "${WAN_SCENARIOS}" ]]; then
  # shellcheck disable=SC2086
  OMP_NUM_THREADS=1 "${PY}" tests/chaos/run_live.py \
    --scenarios ${WAN_SCENARIOS} \
    --baseline 120 --fault 120 --recovery 150 --settle 30 --interval 10 --users "${USERS}" \
    --output "${OUT}/wan" > "${OUT}/system/wan_runner.log" 2>&1
  WAN_RC=$?
  log "wan runner rc=${WAN_RC}"
  # Let latency/heap state from the last WAN recovery settle before the next detector.
  [[ -n "${SERVICE_SCENARIOS}" ]] && sleep 60
fi
SERVICE_RC=skipped
if [[ -n "${SERVICE_SCENARIOS}" ]]; then
  # shellcheck disable=SC2086
  OMP_NUM_THREADS=1 "${PY}" tests/chaos/run_service_faults.py \
    --scenarios ${SERVICE_SCENARIOS} \
    --fault 90 --recovery 150 --users "${USERS}" --interval 10 \
    --output "${OUT}/service" > "${OUT}/system/service_runner.log" 2>&1
  SERVICE_RC=$?
  log "service runner rc=${SERVICE_RC}"
fi
log "campaign ${RUN_ID} end"
echo "CAMPAIGN_DONE ${RUN_ID} wan_rc=${WAN_RC} service_rc=${SERVICE_RC}"
