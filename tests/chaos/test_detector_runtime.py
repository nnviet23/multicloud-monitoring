"""Runtime behavior of the detector: per-entity scoring, exports, alerts, Tempo failures."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine"))
from models.scoring import DualSlidingWindowScorer, MultiEntityScorer  # noqa: E402
from inference.detector import (  # noqa: E402
    ENTITY_FEATURE_COLS,
    EntityCalibrator,
    TempoTraceAnalyzer,
    format_prometheus_metrics,
    format_telegram_alert,
)
from inference.evaluate_test import score_detectors  # noqa: E402
from inference.streaming import TraceEvidence  # noqa: E402


def make_scorer():
    return DualSlidingWindowScorer(0.005, 0.005, 0.35, short_w=3, min_consecutive=2)


class MultiEntityScorerTests(unittest.TestCase):
    def test_breaches_on_different_entities_are_not_a_sustained_anomaly(self):
        scorers = MultiEntityScorer(make_scorer)
        first = scorers.update({"aws:a": (3.0, 1), "azure:b": (0.01, 1)})
        second = scorers.update({"aws:a": (0.01, 2), "azure:b": (3.0, 2)})
        self.assertFalse(MultiEntityScorer.aggregate(first)["is_sustained_anomaly"])
        aggregated = MultiEntityScorer.aggregate(second)
        self.assertFalse(aggregated["is_sustained_anomaly"])
        self.assertTrue(aggregated["is_transient_spike"])

    def test_consecutive_breaches_on_one_entity_are_sustained_and_attributed(self):
        scorers = MultiEntityScorer(make_scorer)
        scorers.update({"aws:a": (0.01, 1), "azure:b": (3.0, 1)})
        aggregated = MultiEntityScorer.aggregate(scorers.update({"aws:a": (0.01, 2), "azure:b": (3.0, 2)}))
        self.assertTrue(aggregated["is_sustained_anomaly"])
        self.assertEqual(aggregated["entity"], "azure:b")
        self.assertEqual(aggregated["sustained_entities"], ["azure:b"])

    def test_repeated_export_is_not_a_second_breach(self):
        scorers = MultiEntityScorer(make_scorer)
        scorers.update({"aws:a": (3.0, "t1")})
        repeated = MultiEntityScorer.aggregate(scorers.update({"aws:a": (3.0, "t1")}))
        self.assertFalse(repeated["is_sustained_anomaly"])
        fresh = MultiEntityScorer.aggregate(scorers.update({"aws:a": (3.0, "t2")}))
        self.assertTrue(fresh["is_sustained_anomaly"])

    def test_empty_results_are_healthy_defaults(self):
        aggregated = MultiEntityScorer.aggregate({})
        self.assertIsNone(aggregated["entity"])
        self.assertFalse(aggregated["is_sustained_anomaly"])


class CalibratorHealthGateTests(unittest.TestCase):
    def test_samples_during_an_incident_are_not_learned_as_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baselines.json"
            path.write_text('{"entities": {}}')
            calibrator = EntityCalibrator(str(path), {k: 1 for k in ENTITY_FEATURE_COLS}, warmup_samples=2)
            raw = {k: 1.0 for k in ENTITY_FEATURE_COLS}
            for _ in range(5):
                calibrator.update_or_standardize("new:svc", raw, response_healthy=False)
            self.assertFalse(calibrator.is_calibrated("new:svc"))
            self.assertEqual(calibrator.rejected_samples["new:svc"], 5)
            for _ in range(2):
                calibrator.update_or_standardize("new:svc", raw, response_healthy=True)
            self.assertTrue(calibrator.is_calibrated("new:svc"))
            overlay = json.loads((Path(directory) / "baselines.runtime.json").read_text())
            self.assertEqual(overlay["entities"]["new:svc"]["rejected_unhealthy_samples"], 5)


class PrometheusExportTests(unittest.TestCase):
    def render(self, verdict="TRANSIENT_SPIKE_SUPPRESSED", tempo_ok=False):
        entity_results = {
            "aws:teastore-webui": {"mse": 0.01, "likelihood_pct": 1.0, "sustained": False},
            "azure:teastore-auth": {"mse": 0.9, "likelihood_pct": 99.0, "sustained": True},
        }
        trace = {"wan_links": {}, "self_times": {}, "db_time_ms": 120.0,
                 "db_entity": "azure:teastore-persistence", "db_target": "MariaDB", "tempo_ok": tempo_ok}
        record = {"verdict": verdict, "model_alert": True, "guard_reasons": []}
        return format_prometheus_metrics(record, entity_results, trace, 50.0, True)

    def test_likelihood_is_per_entity_and_labelled_as_ensemble(self):
        text = self.render()
        self.assertIn('service_name="teastore-webui",model="gru_tcn_ensemble"} 1.00', text)
        self.assertIn('service_name="teastore-auth",model="gru_tcn_ensemble"} 99.00', text)
        self.assertNotIn("gru_autoencoder", text)
        self.assertIn('ai_entity_sustained_anomaly{cloud_provider="azure",service_name="teastore-auth"} 1', text)

    def test_every_verdict_and_tempo_failure_is_exported(self):
        text = self.render()
        self.assertIn('ai_detector_verdict{verdict="TRANSIENT_SPIKE_SUPPRESSED"} 1', text)
        self.assertIn('ai_detector_verdict{verdict="HEALTHY"} 0', text)
        self.assertIn("ai_tempo_query_ok 0", text)
        self.assertIn("ai_detector_model_alert 1", text)
        self.assertIn('component="db",target="MariaDB"} 120.00', text)


class TelegramFormatTests(unittest.TestCase):
    def test_rca_text_is_html_escaped_and_recommendation_matches_cause(self):
        message = format_telegram_alert(
            "azure:teastore-auth", 99.0, 0.9, "ALERT",
            ["[MEMORY_LEAK_GC_STALL] azure:teastore-auth (RAM_Floor=90.0%)", "<script>&"],
            {"wan_links": {}, "self_times": {}, "db_time_ms": 0.0, "tempo_ok": True},
            guard_reasons=[],
        )
        self.assertIn("[MEMORY_LEAK_GC_STALL]", message)
        self.assertIn("&lt;script&gt;&amp;", message)
        self.assertNotIn("<script>", message)
        self.assertIn("heap", message)
        self.assertNotIn("WAN shaping", message)


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TempoFailureTests(unittest.TestCase):
    def analyzer(self):
        analyzer = object.__new__(TempoTraceAnalyzer)
        analyzer.base_url = "http://tempo.invalid"
        analyzer.pf_proc = None
        analyzer.evidence = TraceEvidence()
        return analyzer

    def test_search_failure_is_recorded_instead_of_silently_empty(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            summary = self.analyzer().analyze_recent_traces()
        self.assertFalse(summary["tempo_ok"])
        self.assertTrue(summary["tempo_errors"])

    def test_one_unreadable_trace_does_not_discard_the_others(self):
        search = {"traces": [{"traceID": "bad"}, {"traceID": "good"}]}

        def fake_urlopen(url, timeout=None):
            if "/api/search" in url:
                return _Response(search)
            if url.endswith("/bad"):
                raise urllib.error.URLError("boom")
            return _Response({"batches": []})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            summary = self.analyzer().analyze_recent_traces()
        self.assertTrue(summary["tempo_ok"])
        self.assertEqual(summary["traces_inspected"], 1)
        self.assertEqual(len(summary["tempo_errors"]), 1)


class TraceProbeTests(unittest.TestCase):
    @staticmethod
    def heartbeat(client_cloud, client_service, client_ms, server_ms):
        def resource(cloud, service):
            return {"attributes": [{"key": "cloud.provider", "value": {"stringValue": cloud}},
                                   {"key": "service.name", "value": {"stringValue": service}}]}
        now_ns = int(time.time() * 1e9)
        return {"batches": [
            {"resource": resource(client_cloud, client_service), "scopeSpans": [{"spans": [
                {"spanId": "c", "kind": "SPAN_KIND_CLIENT", "name": "GET",
                 "startTimeUnixNano": now_ns - int(client_ms * 1e6), "endTimeUnixNano": now_ns}]}]},
            {"resource": resource("aws", "teastore-registry"), "scopeSpans": [{"spans": [
                {"spanId": "s", "parentSpanId": "c", "kind": "SPAN_KIND_SERVER", "name": "GET",
                 "startTimeUnixNano": now_ns - int(server_ms * 1e6), "endTimeUnixNano": now_ns}]}]}]}

    def test_short_round_trip_probes_feed_wan_localisation(self):
        now_ns = int(time.time() * 1e9)
        meta = lambda tid, root, age: {"traceID": tid, "rootServiceName": root,
                                       "startTimeUnixNano": str(now_ns - int(age * 1e9)), "durationMs": 25}
        probe_search = {"traces": [meta("rec-old", "teastore-recommender", 20), meta("rec", "teastore-recommender", 3),
                                   meta("auth", "teastore-auth", 2), meta("ui", "teastore-webui", 1)]}
        traces = {"rec": self.heartbeat("gcp", "teastore-recommender", 280, 20),
                  "auth": self.heartbeat("azure", "teastore-auth", 40, 20)}
        fetched = []

        def fake_urlopen(url, timeout=None):
            if "/api/search" in url:
                return _Response(probe_search if "kind" in urllib.parse.unquote_plus(url) else {"traces": []})
            fetched.append(url.rsplit("/", 1)[-1])
            return _Response(traces[fetched[-1]])

        analyzer = TempoFailureTests.analyzer(None)
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            summary = analyzer.analyze_recent_traces()
        self.assertEqual(sorted(fetched), ["auth", "rec"])          # newest per service, webui excluded
        self.assertAlmostEqual(summary["rtt_links"]["gcp->aws (aws:teastore-registry)"], 260, delta=1)
        results = {e: {"raw": {"client_latency_p95": 0.6 if e.startswith("gcp") else 0.02,
                               "server_latency_p95": 0.005, "max_pod_cpu_pct": 5.0}}
                   for e in ("gcp:teastore-recommender", "azure:teastore-auth", "aws:teastore-registry")}
        # The healthy azure round trip is newer than the delayed gcp one, so it exonerates aws/azure.
        self.assertEqual(analyzer.evidence.localize(results, time.time())["cloud"], "gcp")


class EvaluationSeparationTests(unittest.TestCase):
    def test_model_and_guard_are_scored_separately_and_unknown_is_excluded(self):
        records = [
            {"verdict": "ALERT", "model_alert": False, "guard_reasons": ["5xx"]},
            {"verdict": "ALERT", "model_alert": True, "guard_reasons": []},
            {"verdict": "HEALTHY", "model_alert": False, "guard_reasons": []},
            {"verdict": "UNKNOWN", "model_alert": False, "guard_reasons": []},
        ]
        report = score_detectors(records, [True, True, False, True])
        self.assertEqual(report["combined"]["tp"], 2)
        self.assertEqual(report["model_only"]["tp"], 1)
        self.assertEqual(report["model_only"]["fn"], 1)
        self.assertEqual(report["guard_only"]["tp"], 1)
        self.assertEqual(sum(report["combined"][k] for k in ("tp", "tn", "fp", "fn")), 3)


if __name__ == "__main__":
    np.random.seed(0)
    unittest.main()
