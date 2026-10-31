"""Behavior checks for alert persistence, calibration and cloud attribution."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine"))
from data.preprocess import (  # noqa: E402
    split_entities_chronologically,
    compute_entity_baselines,
    build_disjoint_entity_windows,
)
from models.scoring import (  # noqa: E402
    compute_batch_directional_errors,
    validate_likelihood_calibration,
)
from inference.detector import (  # noqa: E402
    DualSlidingWindowScorer, EntityCalibrator, ENTITY_FEATURE_COLS,
    compute_directional_errors, synthesize_multicloud_rca, TempoTraceAnalyzer,
)


class AlertBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.scorer = DualSlidingWindowScorer(0.005, 0.006, 0.35, short_w=3)
        for _ in range(3):
            self.scorer.update_and_score(0.01)

    def test_single_spike_is_suppressed(self):
        spike = self.scorer.update_and_score(3.0)
        self.assertTrue(spike["is_transient_spike"])
        self.assertFalse(spike["is_sustained_anomaly"])
        self.assertFalse(self.scorer.update_and_score(0.01)["is_sustained_anomaly"])

    def test_sustained_fault_alerts_and_recovery_clears(self):
        self.scorer.update_and_score(3.0)
        self.assertTrue(self.scorer.update_and_score(3.0)["is_sustained_anomaly"])
        self.assertFalse(self.scorer.update_and_score(0.01)["is_sustained_anomaly"])

    def test_isolated_spikes_do_not_accumulate(self):
        for score in [3.0, 0.01] * 10:
            self.assertFalse(self.scorer.update_and_score(score)["is_sustained_anomaly"])

    def test_threshold_boundary_is_not_alert(self):
        for _ in range(5):
            self.assertFalse(self.scorer.update_and_score(0.35)["is_sustained_anomaly"])


class CalibrationTests(unittest.TestCase):
    def test_new_cloud_calibrates_and_extreme_values_are_clipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baselines.json"
            path.write_text('{"entities": {}}')
            calibrator = EntityCalibrator(str(path), {k: 1 for k in ENTITY_FEATURE_COLS}, warmup_samples=3)
            raw = {k: 10.0 for k in ENTITY_FEATURE_COLS}
            for _ in range(2):
                z, ready = calibrator.update_or_standardize("new:teastore-test", raw)
                self.assertFalse(ready)
                np.testing.assert_array_equal(z, np.zeros(8))
            _, ready = calibrator.update_or_standardize("new:teastore-test", raw)
            self.assertTrue(ready)
            self.assertIn("new:teastore-test", json.loads(path.read_text())["entities"])
            z, _ = calibrator.update_or_standardize("new:teastore-test", {k: 10000 for k in raw})
            np.testing.assert_array_equal(z, np.full(8, 10.0))


class DirectionalScoringTests(unittest.TestCase):
    def test_faster_healthy_response_does_not_alert_against_old_baseline(self):
        x = torch.zeros(1, 12, 8)
        x[:, :, ENTITY_FEATURE_COLS.index("server_latency_p95")] = -7.0
        healthy, _ = compute_directional_errors(x, torch.zeros_like(x), ENTITY_FEATURE_COLS, True)
        faulty, _ = compute_directional_errors(x, torch.zeros_like(x), ENTITY_FEATURE_COLS, False)
        self.assertEqual(healthy, 0.0)
        self.assertGreater(faulty, 0.35)

    def test_healthy_resource_burst_is_damped(self):
        x = torch.zeros(1, 12, 8)
        x[:, :, ENTITY_FEATURE_COLS.index("max_pod_cpu_pct")] = 2.5
        healthy, _ = compute_directional_errors(x, torch.zeros_like(x), ENTITY_FEATURE_COLS, True)
        faulty, _ = compute_directional_errors(x, torch.zeros_like(x), ENTITY_FEATURE_COLS, False)
        self.assertLess(healthy, faulty)

    def test_recent_fault_has_more_weight_than_old_fault(self):
        old = torch.zeros(1, 12, 8)
        recent = old.clone()
        old[:, 0, 1] = 5.0
        recent[:, -1, 1] = 5.0
        old_score, _ = compute_directional_errors(old, torch.zeros_like(old), ENTITY_FEATURE_COLS, False)
        new_score, _ = compute_directional_errors(recent, torch.zeros_like(recent), ENTITY_FEATURE_COLS, False)
        self.assertGreater(new_score, old_score * 10)


class RootCauseTests(unittest.TestCase):
    def entity(self, **raw_overrides):
        raw = {k: 0.0 for k in ENTITY_FEATURE_COLS}
        raw.update(raw_overrides)
        return {"raw": raw, "mse": 3.0, "z_vec": np.zeros(8), "feat_losses": np.zeros(8)}

    def rca(self, entities, trace):
        return synthesize_multicloud_rca(entities, {}, ENTITY_FEATURE_COLS, trace, False, 700)

    def test_trace_attributes_wan_to_exact_cloud(self):
        causes = self.rca({}, {"wan_links": {"aws->gcp (gcp:teastore-recommender)": 150}})
        self.assertEqual(len(causes), 1)
        self.assertIn("[CROSS_CLOUD_WAN_DELAY] aws->gcp", causes[0])
        self.assertNotIn("azure", causes[0])

    def test_slow_webui_and_downstream_cpu_are_not_proof_of_wan_fault(self):
        entities = {"aws:teastore-webui": self.entity(server_latency_p95=0.7, client_latency_p95=0.2),
                    "gcp:teastore-recommender": self.entity(server_latency_p95=0.5, max_pod_cpu_pct=98)}
        causes = self.rca(entities, {})
        self.assertFalse(any("CROSS_CLOUD_WAN_DELAY" in c for c in causes), causes)

    def test_database_trace_is_classified(self):
        causes = self.rca({}, {"db_time_ms": 200})
        self.assertIn("[DATABASE_BOTTLENECK] azure:teastore-persistence", causes[0])

    def test_normal_wan_delay_does_not_alert(self):
        self.assertEqual(self.rca({}, {"wan_links": {"aws->gcp": 10}}), [])


class TraceDecompositionTests(unittest.TestCase):
    def batch(self, cloud, service, spans):
        return {"resource": {"attributes": [
            {"key": "cloud.provider", "value": {"stringValue": cloud}},
            {"key": "service.name", "value": {"stringValue": service}},
        ]}, "scopeSpans": [{"spans": spans}]}

    def span(self, sid, parent, kind, start_ms, end_ms, **extra):
        return dict(spanId=sid, parentSpanId=parent, kind=kind,
                    startTimeUnixNano=str(start_ms * 1000000),
                    endTimeUnixNano=str(end_ms * 1000000), **extra)

    def decompose(self, batches):
        # Bypass only network setup; exercise the actual trace decomposition.
        analyzer = object.__new__(TempoTraceAnalyzer)
        summary = {"wan_links": {}, "self_times": {}, "server_times": {},
                   "entity_wan_ms": {}, "db_time_ms": 0.0}
        analyzer._decompose_single_trace({"batches": batches}, summary)
        return summary

    def test_client_server_pair_is_attributed_to_destination_cloud(self):
        summary = self.decompose([
            self.batch("aws", "teastore-webui", [self.span("client", "root", "SPAN_KIND_CLIENT", 0, 300)]),
            self.batch("gcp", "teastore-recommender", [self.span("server", "client", "SPAN_KIND_SERVER", 50, 250)]),
        ])
        self.assertEqual(summary["wan_links"], {"aws->gcp (gcp:teastore-recommender)": 100.0})
        self.assertEqual(summary["self_times"]["gcp:teastore-recommender"], 200.0)

    def test_mysql_span_duration_is_extracted(self):
        summary = self.decompose([self.batch("azure", "teastore-persistence", [
            self.span("query", "server", "SPAN_KIND_CLIENT", 0, 120, name="SELECT products",
                      attributes=[{"key": "db.system", "value": {"stringValue": "mysql"}}]),
        ])])
        self.assertEqual(summary["db_time_ms"], 120.0)


class TemporalSplitLeakageTests(unittest.TestCase):
    def test_chronological_split_and_train_only_baselines_have_zero_window_overlap(self):
        rows = []
        for idx in range(40):
            ts = 1793250000.0 + idx * 6.0
            # Validation tail (idx >= 30) deliberately has much higher values to prove
            # baselines are fit strictly on train_df and not leaked from validation.
            val_shift = 100.0 if idx >= 30 else 10.0
            for cp, sn in [("aws", "teastore-webui"), ("gcp", "teastore-recommender")]:
                row = {"timestamp": ts, "cloud_provider": cp, "service_name": sn}
                for col in ENTITY_FEATURE_COLS:
                    row[col] = val_shift
                rows.append(row)
        df = pd.DataFrame(rows)
        train_df, val_df, split_meta = split_entities_chronologically(df, val_split=0.25, window_size=6)

        # 1. Every entity's train timestamps must strictly precede its validation timestamps
        for eid, info in split_meta.items():
            self.assertLess(info["train_end_ts"], info["val_start_ts"], eid)

        # 2. Baselines computed on train_df must not see the 100.0 validation shift
        scale_floors = {col: 1.0 for col in ENTITY_FEATURE_COLS}
        baselines = compute_entity_baselines(train_df, ENTITY_FEATURE_COLS, scale_floors)
        for eid, b_info in baselines.items():
            self.assertEqual(b_info["fit_scope"], "train_only")
            self.assertAlmostEqual(b_info["features"]["qps"]["median"], 10.0, places=5)

        # 3. Sliding windows built from train_df and val_df must share zero timestamps
        X_train, X_val, win_counts = build_disjoint_entity_windows(
            train_df, val_df, baselines, ENTITY_FEATURE_COLS, window_size=6, stride=1
        )
        self.assertGreater(len(X_train), 0)
        self.assertGreater(len(X_val), 0)
        for eid, c_info in win_counts.items():
            self.assertGreater(c_info["train_windows"], 0, eid)
            self.assertGreater(c_info["val_windows"], 0, eid)
        # Verify validation windows standardized against train-only baselines reflect +10z shift
        np.testing.assert_allclose(X_val, 10.0, rtol=1e-5, atol=1e-5)


class UnifiedScoringAndLikelihoodCalibrationTests(unittest.TestCase):
    def test_training_batch_and_inference_single_scoring_are_identical(self):
        rng = np.random.default_rng(42)
        x_np = rng.normal(0.0, 2.5, size=(8, 12, len(ENTITY_FEATURE_COLS))).astype(np.float32)
        rec_np = rng.normal(0.0, 0.5, size=(8, 12, len(ENTITY_FEATURE_COLS))).astype(np.float32)

        for healthy in (True, False):
            batch_mse, batch_feat = compute_batch_directional_errors(
                x_np, rec_np, ENTITY_FEATURE_COLS, healthy_mask=healthy
            )
            for i in range(len(x_np)):
                single_mse, single_feat = compute_directional_errors(
                    torch.from_numpy(x_np[i:i + 1]),
                    torch.from_numpy(rec_np[i:i + 1]),
                    ENTITY_FEATURE_COLS,
                    is_response_healthy=healthy,
                )
                self.assertAlmostEqual(float(batch_mse[i]), float(single_mse), places=6)
                np.testing.assert_allclose(batch_feat[i], single_feat, rtol=1e-5, atol=1e-6)

    def test_calibrated_likelihood_is_anchored_at_threshold_and_validated(self):
        scorer = DualSlidingWindowScorer(base_mean=0.004, base_std=0.005, threshold=0.35, short_w=3)
        self.assertAlmostEqual(scorer.compute_likelihood(0.004), 0.01, places=6)
        self.assertLess(scorer.compute_likelihood(0.20), 0.50)
        self.assertAlmostEqual(scorer.compute_likelihood(0.35), 0.50, places=6)
        self.assertGreater(scorer.compute_likelihood(0.55), 0.50)

        normal_mse = np.linspace(0.001, 0.03, 50, dtype=np.float64)
        fault_mse = np.linspace(0.80, 3.50, 50, dtype=np.float64)
        cal_report = validate_likelihood_calibration(
            normal_mse_array=normal_mse,
            fault_mse_array=fault_mse,
            base_mean=0.004,
            base_std=0.005,
            threshold=0.35,
            dw_cfg={"short_window": 3, "long_window": 18, "min_consecutive_breaches": 2},
        )
        self.assertTrue(cal_report["calibration_verified"])
        self.assertLess(cal_report["brier_score"], 0.05)
        self.assertLess(cal_report["expected_calibration_error"], 0.10)
        self.assertEqual(cal_report["threshold_anchor_prob_pct"], 50.0)


if __name__ == "__main__":
    torch.set_num_threads(1)
    unittest.main()
