"""Data-driven health limits for SLO guards, recovery confirmation and RCA gating.

The detector used fixed latency limits (probe 480/500 ms, WebUI P95 520/550 ms,
entity server P95 0.25/0.50 s, client P95 0.05 s) tuned for the earlier
3-cluster lab. On the 4-cluster lab a fault-free WebUI request already crosses the
simulated WAN many times, so normal latency sits close to those limits.

`fit_slo_guards` derives the limits from fault-free training data (entity rows
and detector-equivalent probe logs). Every limit keeps the old constant as a
floor, so learned limits can only relax a limit that normal traffic already
breaches; they never make a guard more sensitive than before. `GuardLimits`
falls back to the old constants when no learned limits exist.
"""
import math

import numpy as np

# Former hard-coded constants (used as floors and as defaults).
DEFAULTS = {
    "probe_healthy_ms": 480.0,       # cluster considered responsive below this
    "probe_slow_ms": 500.0,          # slow-probe streak / SLO breach at or above this
    "probe_recovered_ms": 400.0,     # probe counts as recovery evidence below this
    "entry_healthy_ms": 520.0,       # entrypoint (WebUI) server P95 for cluster health
    "entry_slo_ms": 550.0,           # entrypoint server P95 SLO breach
    "server_healthy_s": 0.50,        # per-entity server P95 for response-healthy scoring
    "server_recovered_s": 0.25,      # per-entity server P95 that confirms recovery
    "client_healthy_s": 0.05,        # per-entity client P95 for response-healthy scoring
}

# Margins over the fault-free tail. Healthy/SLO limits use p99.5 x 1.3; recovery
# limits are stricter (p99 x 1.1) so an alert clears only on clearly normal data.
HEALTHY_MARGIN = 1.3
RECOVERY_MARGIN = 1.1


def _tail(values, q):
    values = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=np.float64)
    return float(np.percentile(values, q)) if len(values) else None


def fit_slo_guards(entity_rows, probe_ms=None, entrypoint="aws:teastore-webui", min_rows=60):
    """Fit limits from fault-free data.

    `entity_rows`: DataFrame with cloud_provider, service_name, server_latency_p95,
    client_latency_p95. `probe_ms`: latencies of successful detector probes.
    """
    guards = {"method": f"max(old_constant, p99.5 x {HEALTHY_MARGIN}); recovery max(old_constant, p99 x {RECOVERY_MARGIN})",
              "global": dict(DEFAULTS), "entities": {}, "evidence": {}}
    for (cp, sn), grp in entity_rows.groupby(["cloud_provider", "service_name"]):
        if len(grp) < min_rows:
            continue
        eid = f"{cp}:{sn}"
        server, client = grp["server_latency_p95"].to_numpy(), grp["client_latency_p95"].to_numpy()
        guards["entities"][eid] = {
            "server_healthy_s": round(max(DEFAULTS["server_healthy_s"], HEALTHY_MARGIN * _tail(server, 99.5)), 4),
            "server_recovered_s": round(max(DEFAULTS["server_recovered_s"], RECOVERY_MARGIN * _tail(server, 99)), 4),
            "client_healthy_s": round(max(DEFAULTS["client_healthy_s"], HEALTHY_MARGIN * _tail(client, 99.5)), 4),
        }
        guards["evidence"][eid] = {"rows": int(len(grp)),
                                   "server_p99_s": round(_tail(server, 99), 4), "server_p99_5_s": round(_tail(server, 99.5), 4),
                                   "client_p99_s": round(_tail(client, 99), 4), "client_p99_5_s": round(_tail(client, 99.5), 4)}
    entry = guards["entities"].get(entrypoint)
    g = guards["global"]
    if entry:
        g["entry_healthy_ms"] = round(max(DEFAULTS["entry_healthy_ms"], entry["server_healthy_s"] * 1000.0 + 20.0), 1)
        g["entry_slo_ms"] = round(max(DEFAULTS["entry_slo_ms"], entry["server_healthy_s"] * 1000.0 + 50.0), 1)
    probes = [p for p in (probe_ms if probe_ms is not None else []) if p is not None and math.isfinite(p)]
    if len(probes) >= min_rows:
        p995, p99 = _tail(probes, 99.5), _tail(probes, 99)
        g["probe_slow_ms"] = round(max(DEFAULTS["probe_slow_ms"], HEALTHY_MARGIN * p995), 1)
        g["probe_healthy_ms"] = round(max(DEFAULTS["probe_healthy_ms"], g["probe_slow_ms"] - 20.0), 1)
        g["probe_recovered_ms"] = round(max(DEFAULTS["probe_recovered_ms"], RECOVERY_MARGIN * p99), 1)
        guards["evidence"]["probe"] = {"samples": len(probes), "p99_ms": round(p99, 1), "p99_5_ms": round(p995, 1)}
    return guards


class GuardLimits:
    """Read limits learned by `fit_slo_guards`, falling back to the old constants."""

    def __init__(self, guards=None):
        guards = guards or {}
        self.global_limits = {**DEFAULTS, **guards.get("global", {})}
        self.entities = guards.get("entities", {})

    def __getattr__(self, name):
        limits = self.__dict__.get("global_limits", {})
        if name in limits:
            return limits[name]
        raise AttributeError(name)

    def entity(self, eid, name):
        value = self.entities.get(eid, {}).get(name)
        if value is None:
            service = eid.split(":", 1)[-1]
            value = next((v.get(name) for k, v in self.entities.items() if k.endswith(":" + service) and name in v), None)
        return float(value if value is not None else DEFAULTS[name])
