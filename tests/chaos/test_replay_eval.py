"""Offline replay labelling and fault summary logic."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine"))

from inference.replay_eval import episodes, epoch, samples_from_chaos, summarize_faults  # noqa: E402

FEATURES = {"qps": 1.0, "server_latency_p95": 0.01, "client_latency_p95": 0.02, "error_rate_5xx": 0.0,
            "max_pod_cpu_pct": 5.0, "max_pod_ram_pct": 40.0, "ram_floor_2m_pct": 35.0, "gc_pause_rate": 0.001}


def iso(seconds):
    return f"2099-01-01T00:{seconds // 60:02d}:{seconds % 60:02d}Z"


class ReplayLabelTest(unittest.TestCase):
    def write_run(self, tmp):
        phases = [{"id": "baseline", "start": iso(0), "end": iso(120)},
                  {"id": "cpu", "start": iso(120), "end": iso(240)},
                  {"id": "recovery_after_cpu", "start": iso(240), "end": iso(420)}]
        records = [{"timestamp": iso(t), "telemetry_complete": t != 60,
                    "entity_features": {"gcp:teastore-recommender": FEATURES},
                    "entity_response_healthy": {"gcp:teastore-recommender": True}, "fast_metrics": {}}
                   for t in range(0, 420, 10)]
        (tmp / "events.json").write_text(json.dumps({"phases": phases}))
        (tmp / "detector.json").write_text(json.dumps({"records": records}))
        return phases

    def test_labels_respect_settle_and_skip_incomplete_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.write_run(tmp)
            _, samples, _ = samples_from_chaos(tmp, settle=30)
        by_t = {int(s["t"]) % 3600: s["label"] for s in samples}
        self.assertNotIn(60, by_t)              # telemetry incomplete -> not scored
        self.assertEqual(by_t[30], 0)           # baseline after settle
        self.assertIsNone(by_t[20])             # baseline settle
        self.assertIsNone(by_t[130])            # fault settle
        self.assertEqual(by_t[150], 1)          # fault after settle
        self.assertIsNone(by_t[250])            # recovery settle

    def test_fault_summary_counts_detection_and_localization(self):
        with tempfile.TemporaryDirectory() as tmp:
            phases = self.write_run(Path(tmp))
        scored = []
        base = epoch(iso(0))
        for t in range(0, 420, 10):
            label = 1 if 150 <= t < 240 else (0 if 30 <= t < 120 or t >= 270 else None)
            alert = 170 <= t < 250
            scored.append({"t": base + t, "label": label, "alert": alert,
                           "entities": ["gcp:teastore-recommender"] if alert else []})
        summary = summarize_faults("run", scored, phases, settle=30)
        row = summary["faults"][0]
        self.assertTrue(row["detected"])
        self.assertTrue(row["localized"])
        self.assertEqual(row["detection_seconds"], 50.0)
        self.assertEqual(summary["normal_phase_alert_samples"], 0)  # t=240 alert is unlabelled settle
        self.assertEqual(episodes([False, True, True, False, True]), 2)


if __name__ == "__main__":
    unittest.main()
