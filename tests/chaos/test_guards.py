"""Learned SLO guard limits: floors, fallbacks, recovery use and train-only probes."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine"))

from models.guards import DEFAULTS, GuardLimits, fit_slo_guards  # noqa: E402
from inference.streaming import LatencyRecovery  # noqa: E402
from data.preprocess import load_training_probes  # noqa: E402


def rows(entity, server, client, n=200):
    cp, sn = entity.split(":")
    return pd.DataFrame({"cloud_provider": cp, "service_name": sn,
                         "server_latency_p95": np.full(n, server), "client_latency_p95": np.full(n, client)})


class GuardFitTests(unittest.TestCase):
    def test_limits_never_drop_below_old_constants(self):
        guards = fit_slo_guards(rows("aws:teastore-image", 0.005, 0.005), probe_ms=[100.0] * 100)
        limits = GuardLimits(guards)
        self.assertEqual(limits.entity("aws:teastore-image", "server_healthy_s"), DEFAULTS["server_healthy_s"])
        self.assertEqual(limits.probe_slow_ms, DEFAULTS["probe_slow_ms"])

    def test_slow_normal_entrypoint_relaxes_its_limits_only(self):
        df = pd.concat([rows("aws:teastore-webui", 0.46, 0.005), rows("azure:teastore-auth", 0.005, 0.024)])
        limits = GuardLimits(fit_slo_guards(df, probe_ms=list(np.linspace(330, 450, 200))))
        self.assertAlmostEqual(limits.entity("aws:teastore-webui", "server_healthy_s"), round(0.46 * 1.3, 4))
        self.assertAlmostEqual(limits.entity("aws:teastore-webui", "server_recovered_s"), round(0.46 * 1.1, 4))
        self.assertEqual(limits.entity("azure:teastore-auth", "server_healthy_s"), 0.5)
        self.assertGreater(limits.entry_slo_ms, 0.46 * 1300)
        self.assertGreater(limits.probe_slow_ms, 500.0)
        self.assertLess(limits.probe_healthy_ms, limits.probe_slow_ms)

    def test_defaults_and_service_fallback(self):
        self.assertEqual(GuardLimits().probe_slow_ms, 500.0)
        limits = GuardLimits(fit_slo_guards(rows("aws:teastore-webui", 0.46, 0.005)))
        # A scaled-out/moved service keeps its learned limit.
        self.assertAlmostEqual(limits.entity("gcp:teastore-webui", "server_healthy_s"), round(0.46 * 1.3, 4))
        self.assertEqual(limits.entity("new:unknown", "client_healthy_s"), 0.05)

    def test_recovery_accepts_normal_slow_entrypoint_with_learned_limits(self):
        def obs(t, value):
            return {"value": value, "observed_at": t, "fresh": True, "requests": 10}
        strict, learned = LatencyRecovery(), LatencyRecovery(
            limits=GuardLimits(fit_slo_guards(rows("aws:teastore-webui", 0.46, 0.005), probe_ms=[400.0] * 100)))
        for t in (1, 2):
            strict_ok = strict.update("aws:teastore-webui", obs(t, 0.45), None, True, 420)
            learned_ok = learned.update("aws:teastore-webui", obs(t, 0.45), None, True, 420)
        self.assertFalse(strict_ok)
        self.assertTrue(learned_ok)


class TrainOnlyProbeTests(unittest.TestCase):
    def test_probes_during_validation_rows_are_excluded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "raw" / "run01"
            (run / "workload").mkdir(parents=True)
            (run / "metrics").mkdir()
            csv = run / "metrics" / "entity_features.csv"
            pd.DataFrame({"timestamp": [0, 10, 20, 30], "probe_ok": [1, 1, 1, 0], "probe_ms": [100, 200, 300, 400],
                          "datetime": "", "probe_code": 200}).to_csv(run / "workload" / "probe.csv", index=False)
            df = pd.DataFrame({"source_run": "run01", "timestamp": [0, 10, 20, 30],
                               "split": ["train", "val", "train", "train"]})
            kept, sources = load_training_probes(df, [str(csv)])
        self.assertEqual(sorted(kept), [100.0, 300.0])   # val-time probe and failed probe excluded
        self.assertEqual(sources[0]["probes_in_train"], 2)


if __name__ == "__main__":
    unittest.main()
