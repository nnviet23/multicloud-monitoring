"""Regression checks for fresh evidence, recovery, and incident attribution."""
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai-engine"))
from data.preprocess import impute_causally
from inference.streaming import HistogramDeltas, LatencyRecovery, TraceEvidence
from models.scoring import DualSlidingWindowScorer
from inference.detector import PrometheusVectorClient, probe_webui_health


class CausalImputationTests(unittest.TestCase):
    def test_no_future_or_other_entity_values_and_validation_carries_training_tail(self):
        def rows(cloud, values, start=0):
            return [{"cloud_provider": cloud, "service_name": "teastore-test",
                     "timestamp": start + i, "qps": value} for i, value in enumerate(values)]
        train = pd.DataFrame(rows("aws", [np.nan, 10, np.nan]) + rows("gcp", [np.nan, np.nan, np.nan]))
        val = pd.DataFrame(rows("aws", [np.nan, 99, np.nan], 3) + rows("gcp", [np.nan, 50, np.nan], 3))
        t, v = impute_causally(train, val, ["qps"])
        self.assertEqual(t[t.cloud_provider == "aws"].qps.tolist(), [0, 10, 10])
        self.assertEqual(t[t.cloud_provider == "gcp"].qps.tolist(), [0, 0, 0])
        self.assertEqual(v[v.cloud_provider == "aws"].qps.tolist(), [10, 99, 99])
        self.assertEqual(v[v.cloud_provider == "gcp"].qps.tolist(), [0, 50, 50])


class HistogramTests(unittest.TestCase):
    def setUp(self):
        self.tracker = HistogramDeltas(max_age=20)
        self.counts = {0.05: 50, 0.5: 100, math.inf: 100}

    def test_p95_describes_new_requests_without_old_slow_ones(self):
        self.assertIsNone(self.tracker.update("service", self.counts, 0))
        new = {0.05: 150, 0.5: 200, math.inf: 200}
        result = self.tracker.update("service", new, 10)
        self.assertAlmostEqual(result["value"], 0.0475)
        self.assertTrue(result["fresh"])
        self.assertEqual(result["requests"], 100)

    def test_repeated_or_expired_counters_do_not_become_fresh_evidence(self):
        self.tracker.update("service", self.counts, 0)
        new = {bound: count + 100 for bound, count in self.counts.items()}
        self.tracker.update("service", new, 10)
        self.assertFalse(self.tracker.update("service", new, 16)["fresh"])
        self.assertIsNone(self.tracker.update("service", new, 31))
        self.assertIsNone(self.tracker.update("missing", {}, 10))

    def test_counter_reset_cannot_be_interpreted_as_recovery(self):
        self.tracker.update("service", self.counts, 0)
        self.assertIsNone(self.tracker.update("service", {k: 0 for k in self.counts}, 10))


class RecoveryTests(unittest.TestCase):
    def observation(self, when, value=0.02, fresh=True):
        return {"observed_at": when, "value": value, "fresh": fresh}

    def test_probe_alone_or_repeated_export_cannot_clear_a_fault(self):
        recovery = LatencyRecovery()
        self.assertFalse(recovery.update("e", None, None, True, 20))
        self.assertFalse(recovery.update("e", self.observation(10), self.observation(10), True, 20))
        self.assertFalse(recovery.update("e", self.observation(10, fresh=False), self.observation(10), True, 20))
        self.assertTrue(recovery.update("e", self.observation(20), self.observation(20), True, 20))

    def test_slow_or_missing_client_and_errors_block_recovery(self):
        recovery = LatencyRecovery()
        for when in (10, 20, 30):
            self.assertFalse(recovery.update("e", self.observation(when), self.observation(when, 0.3), True, 20))
            self.assertFalse(recovery.update("e", self.observation(when), None, True, 20, client_required=True))
            self.assertFalse(recovery.update("e", self.observation(when), self.observation(when), True, 20, error_rate=1))

    def test_latency_refresh_preserves_memory_cpu_and_gc_fault_history(self):
        features = ["server_latency_p95", "client_latency_p95", "max_pod_cpu_pct", "ram_floor_2m_pct", "gc_pause_rate"]
        buffer = [np.array([7, 7, 9, 8, 6], dtype=float) for _ in range(12)]
        LatencyRecovery.refresh_latency_history(buffer, np.zeros(5), features)
        for row in buffer:
            np.testing.assert_array_equal(row, [0, 0, 9, 8, 6])

    def test_refresh_never_amplifies_a_new_spike_into_a_full_fault_window(self):
        buffer = [np.array([0, 0], dtype=float), np.array([8, 8], dtype=float)]
        LatencyRecovery.refresh_latency_history(buffer, np.array([3, 0]), ["server_latency_p95", "client_latency_p95"])
        np.testing.assert_array_equal(buffer, [[0, 0], [3, 0]])

    def test_current_saturation_is_never_cleared_and_memory_gc_history_survives_cpu_recovery(self):
        features = ["max_pod_cpu_pct", "ram_floor_2m_pct", "gc_pause_rate"]
        buffer = [np.array([8, 9, 7], dtype=float) for _ in range(12)]
        self.assertFalse(LatencyRecovery.refresh_cpu_history(buffer, np.array([8, 0, 0]), features, 100, True))
        self.assertFalse(LatencyRecovery.refresh_cpu_history(buffer, np.array([0, 0, 0]), features, 5, False))
        self.assertTrue(LatencyRecovery.refresh_cpu_history(buffer, np.array([0, 0, 0]), features, 5, True))
        for row in buffer:
            np.testing.assert_array_equal(row, [0, 9, 7])

    def test_error_history_requires_the_additional_export_confirmation(self):
        features = ["server_latency_p95", "client_latency_p95", "error_rate_5xx", "ram_floor_2m_pct"]
        buffer = [np.array([6, 6, 8, 9], dtype=float)]
        LatencyRecovery.refresh_latency_history(buffer, np.zeros(4), features)
        np.testing.assert_array_equal(buffer[0], [0, 0, 8, 9])
        LatencyRecovery.refresh_latency_history(buffer, np.zeros(4), features, include_errors=True)
        np.testing.assert_array_equal(buffer[0], [0, 0, 0, 9])

    def test_several_new_requests_and_independent_probes_confirm_without_waiting_another_export(self):
        recovery = LatencyRecovery()
        self.assertFalse(recovery.update("e", None, None, True, 20))
        self.assertFalse(recovery.update("e", None, None, True, 20))
        server = {**self.observation(20), "requests": 10}
        client = {**self.observation(20), "requests": 5}
        self.assertTrue(recovery.update("e", server, client, True, 20, client_required=True))


class TraceEvidenceTests(unittest.TestCase):
    link = "aws->gcp (gcp:teastore-recommender)"

    def entities(self):
        return {"gcp:teastore-recommender": {"raw": {"client_latency_p95": 0.3, "server_latency_p95": 0.01}}}

    def test_trace_gap_keeps_original_evidence_and_expiry(self):
        cache = TraceEvidence(ttl=30)
        cache.observe({"wan_links": {self.link: 250}}, "trace-1", 100, 100)
        evidence = cache.active(self.entities(), 120)[self.link]
        self.assertEqual(evidence["trace_id"], "trace-1")
        self.assertEqual(evidence["age_seconds"], 20)
        self.assertEqual(cache.active(self.entities(), 131), {})

    def test_recovery_invalidates_trace_and_prevents_old_trace_reintroduction(self):
        cache = TraceEvidence()
        cache.observe({"wan_links": {self.link: 250}}, "trace-1", 100, 100)
        cache.forget("gcp:teastore-recommender", now=110)
        cache.observe({"wan_links": {self.link: 250}}, "trace-1", 100, 115)
        self.assertEqual(cache.active(self.entities(), 115), {})
        cache.observe({"wan_links": {self.link: 250}}, "new-fault", 120, 120)
        self.assertIn(self.link, cache.active(self.entities(), 120))

    def test_healthy_or_unrelated_entity_never_inherits_wan_attribution(self):
        cache = TraceEvidence()
        cache.observe({"wan_links": {self.link: 250}}, "trace", 100, 100)
        self.assertEqual(cache.active({}, 110), {})
        healthy = {"gcp:teastore-recommender": {"raw": {"client_latency_p95": 0.01, "server_latency_p95": 0.01}}}
        self.assertEqual(cache.active(healthy, 110), {})

    def test_client_cpu_saturation_invalidates_ambiguous_wan_evidence(self):
        cache = TraceEvidence()
        cache.observe({"wan_links": {self.link: 250}}, "trace", 100, 100)
        entities = self.entities()
        entities["aws:teastore-webui"] = {"raw": {"max_pod_cpu_pct": 99}}
        self.assertEqual(cache.active(entities, 110), {})

    def test_db_trace_evidence_retains_incident_and_clears_on_recovery(self):
        cache = TraceEvidence(ttl=45)
        cache.observe({"db_time_ms": 340.0, "wan_links": {}}, "db-trace-1", 100, 105)
        entities = {"azure:teastore-persistence": {"mse": 2.1, "raw": {"server_latency_p95": 0.34, "client_latency_p95": 0.01}}}
        active = cache.active_db(entities, 130)
        self.assertIsNotNone(active)
        self.assertEqual(active["trace_id"], "db-trace-1")
        self.assertEqual(active["age_seconds"], 30)
        cache.forget("azure:teastore-persistence", now=135)
        cache.observe({"db_time_ms": 340.0, "wan_links": {}}, "db-trace-1", 100, 140)
        self.assertIsNone(cache.active_db(entities, 140))


class LikelihoodRecoveryTests(unittest.TestCase):
    def test_duplicate_export_cannot_confirm_a_new_anomaly(self):
        scorer = DualSlidingWindowScorer(0.005, 0.005, 0.35, short_w=3)
        self.assertFalse(scorer.update_and_score(3)["is_sustained_anomaly"])
        self.assertFalse(scorer.update_and_score(3, new_observation=False)["is_sustained_anomaly"])
        self.assertTrue(scorer.update_and_score(3)["is_sustained_anomaly"])

    def test_recovery_score_does_not_retain_window_only_fault_probability(self):
        scorer = DualSlidingWindowScorer(0.005, 0.005, 0.35, short_w=3)
        for _ in range(3):
            scorer.update_and_score(3)
        result = scorer.update_and_score(0.01)
        self.assertFalse(result["is_sustained_anomaly"])
        self.assertLess(result["likelihood_pct"], 50)
        self.assertGreater(result["window_likelihood_pct"], 50)


class MissingTelemetryTests(unittest.TestCase):
    def test_connection_failure_is_recorded_instead_of_becoming_healthy_zero_metrics(self):
        client = object.__new__(PrometheusVectorClient)
        client.base_url = "http://unavailable.invalid"
        client.query_failures = []
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertEqual(client.query_vector("metric"), [])
        self.assertEqual(client.query_failures, ["metric"])

    def test_http_5xx_probe_retains_status_for_slo_diagnostics(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("http://test", 502, "Bad Gateway", {}, None)):
            ok, status, latency = probe_webui_health()
        self.assertFalse(ok)
        self.assertEqual(status, 502)


if __name__ == "__main__":
    unittest.main()
