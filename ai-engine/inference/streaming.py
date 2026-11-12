"""Fresh counter deltas, bounded trace evidence, and latency recovery state."""
import math

from models.guards import GuardLimits


class HistogramDeltas:
    """Quantiles from consecutive cumulative histogram exports, not a 1m average.

    Repeated counters are not new evidence. Resets/bucket changes restart the
    baseline; missing or idle histograms never become a synthetic zero latency.
    """
    def __init__(self, max_age=20.0):
        self.max_age = max_age
        self.previous = {}
        self.latest = {}

    @staticmethod
    def quantile(buckets, quantile=0.95):
        total = buckets.get(math.inf, 0.0)
        if total <= 0:
            return None
        target, previous_count, previous_bound = total * quantile, 0.0, 0.0
        for bound, count in sorted(buckets.items()):
            count = max(previous_count, count)
            if count >= target:
                if math.isinf(bound):
                    return previous_bound
                fraction = (target - previous_count) / max(count - previous_count, 1e-12)
                return previous_bound + fraction * (bound - previous_bound)
            previous_count, previous_bound = count, bound
        return None

    def update(self, key, buckets, now):
        old = self.previous.get(key)
        fresh = False
        if buckets and old is not None and buckets.keys() == old.keys():
            delta = {bound: buckets[bound] - old[bound] for bound in buckets}
            if all(value >= 0 for value in delta.values()):
                value = self.quantile(delta)
                if value is not None:
                    self.latest[key] = {"value": value, "observed_at": now,
                                        "requests": delta[math.inf]}
                    fresh = True
            else:
                self.latest.pop(key, None)
        elif old is not None:
            self.latest.pop(key, None)
        if buckets:
            self.previous[key] = dict(buckets)
        result = self.latest.get(key)
        if result is None or now - result["observed_at"] > self.max_age:
            return None
        return {**result, "fresh": fresh, "age_seconds": now - result["observed_at"]}


class LatencyRecovery:
    """Require fresh completed requests and repeated independent HTTP probes.

    Latency/error recovery and independently confirmed low CPU have separate
    rules. Memory and GC history is retained throughout.
    """
    def __init__(self, confirmations=2, min_requests=5, limits=None):
        self.confirmations = confirmations
        self.min_requests = min_requests
        self.limits = limits or GuardLimits()
        self.state = {}

    def update(self, entity, server, client, probe_ok, probe_ms, error_rate=0.0, client_required=False):
        state = self.state.setdefault(entity, {"count": 0, "token": None, "probes": 0})
        probe_limit = self.limits.probe_recovered_ms
        state["probes"] = state["probes"] + 1 if probe_ok and probe_ms < probe_limit else 0
        healthy = (server is not None and (not client_required or client is not None)
                   and server["value"] < self.limits.entity(entity, "server_recovered_s")
                   and (client is None or client["value"] < self.limits.entity(entity, "client_healthy_s"))
                   and probe_ok and probe_ms < probe_limit and error_rate == 0.0)
        if not healthy:
            state["count"] = 0
            return False
        token = (server["observed_at"], client["observed_at"] if client else None)
        if token == state["token"] or not server["fresh"]:
            return False
        state["token"] = token
        state["count"] += 1
        # A fresh batch containing several completed requests plus repeated
        # independent end-to-end probes also confirms recovery. Waiting for a
        # second export adds a full SDK/scrape interval without new information.
        batch_confirmed = (server.get("requests", 0) >= self.min_requests
                           and (not client_required or client.get("requests", 0) >= 1)
                           and state["probes"] >= self.confirmations)
        return state["count"] >= self.confirmations or batch_confirmed

    @staticmethod
    def refresh_latency_history(buffer, current, features, include_errors=False):
        for row in buffer:
            names = ("server_latency_p95", "client_latency_p95") + (("error_rate_5xx",) if include_errors else ())
            for name in names:
                if name not in features:
                    continue
                index = features.index(name)
                row[index] = min(row[index], current[index])

    @staticmethod
    def refresh_cpu_history(buffer, current, features, cpu_pct, confirmed):
        """Clear historical saturation only after a fresh, near-baseline CPU reading.

        A batch/probe confirmation alone never clears CPU; the current JVM CPU
        must also be low in both physical and standardized units. Heap/GC stay.
        """
        index = features.index("max_pod_cpu_pct")
        if not confirmed or cpu_pct >= 60 or current[index] >= 1.5:
            return False
        if not any(row[index] > 2.0 for row in buffer):
            return False
        for row in buffer:
            row[index] = min(row[index], current[index])
        return True


class TraceEvidence:
    """Keep trace-supported WAN candidates with trace ID, age and TTL.

    Cached evidence explains an alert; it never drives model input or SLO guards.
    Reading the cache cannot extend its expiry. Recovery invalidates the entity.
    """
    def __init__(self, ttl=90.0, limits=None):
        self.ttl = ttl
        self.limits = limits or GuardLimits()
        self.links = {}
        self.db = None
        self.cleared_at = {}

    def observe(self, summary, trace_id, observed_at, now):
        if observed_at > now + 5 or now - observed_at > self.ttl:
            return
        db_ms = summary.get("db_time_ms", 0.0)
        db_entity = summary.get("db_entity") or "azure:teastore-persistence"
        db_target = summary.get("db_target") or "MariaDB"
        if (math.isfinite(db_ms) and db_ms >= 80.0
                and observed_at > self.cleared_at.get(db_entity, -math.inf)):
            if self.db is None or observed_at > self.db["observed_at"]:
                self.db = {"db_time_ms": db_ms, "trace_id": trace_id,
                           "observed_at": observed_at, "entity": db_entity,
                           "target": db_target}
        for link, delay in summary.get("wan_links", {}).items():
            if not math.isfinite(delay) or delay < 65.0 or " (" not in link:
                continue
            path, entity = link.split(" (", 1)
            if "->" not in path:
                continue
            source, destination = path.split("->", 1)
            entity = entity.rstrip(")")
            if observed_at <= self.cleared_at.get(entity, -math.inf):
                continue
            if source == destination:
                continue
            previous = self.links.get(link)
            if previous is None or observed_at > previous["observed_at"]:
                self.links[link] = {"delay_ms": delay, "trace_id": trace_id,
                                    "observed_at": observed_at, "entity": entity}

    @staticmethod
    def supported(link, entity_results):
        """Client-side CPU saturation can inflate client/server span residuals."""
        source = link.split("->", 1)[0]
        target = link.split(" (", 1)[-1].rstrip(")")
        return not any(result["raw"].get("max_pod_cpu_pct", 0) >= 85
                       for eid, result in entity_results.items()
                       if eid.startswith(source + ":") or eid == target)

    def forget(self, entity, now=None):
        self.links = {link: value for link, value in self.links.items() if value["entity"] != entity}
        if self.db is not None and self.db.get("entity") == entity:
            self.db = None
        if now is not None:
            self.cleared_at[entity] = now

    def active_db(self, entity_results, now):
        if self.db is None or not (0 <= now - self.db["observed_at"] <= self.ttl):
            self.db = None
            return None
        entity = entity_results.get(self.db["entity"])
        if entity is None:
            return None
        raw = entity["raw"]
        any_entrypoint_slow = any(
            r["raw"].get("server_latency_p95", 0.0) > self.limits.entity(eid, "server_healthy_s")
            for eid, r in entity_results.items()
        )
        if raw["server_latency_p95"] <= 0.05 and entity.get("mse", 0.0) <= 0.35 and not any_entrypoint_slow:
            return None
        return {**self.db, "age_seconds": round(now - self.db["observed_at"], 1)}

    def active(self, entity_results, now):
        self.links = {link: value for link, value in self.links.items()
                      if 0 <= now - value["observed_at"] <= self.ttl and self.supported(link, entity_results)}
        result = {}
        for link, value in self.links.items():
            entity = entity_results.get(value["entity"])
            if entity is None:
                continue
            raw = entity["raw"]
            eid = value["entity"]
            if (raw["client_latency_p95"] <= self.limits.entity(eid, "client_healthy_s")
                    and raw["server_latency_p95"] <= self.limits.entity(eid, "server_recovered_s")):
                continue
            result[link] = {**value, "age_seconds": round(now - value["observed_at"], 1)}
        return result
