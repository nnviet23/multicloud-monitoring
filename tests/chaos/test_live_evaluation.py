"""Ensure a live test cannot pass on SLO guards or missing telemetry alone."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("run_live", Path(__file__).with_name("run_live.py"))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveEvaluationTests(unittest.TestCase):
    def phase(self, name):
        return {"id": name, "start": "2026-10-30T00:00:00+00:00", "end": "2026-10-30T00:01:00+00:00"}

    def records(self, model=True, cause="[CROSS_CLOUD_WAN_DELAY] aws->gcp", **overrides):
        return [dict(timestamp=f"2026-10-30T00:00:{second:02d}Z", verdict="ALERT",
                     model_alert=model, rca_causes=[cause], entity_count=6,
                     probe_ok=True, probe_ms=50, **overrides) for second in [36, 42, 48]]

    def test_fault_requires_both_model_and_correct_cloud_rca(self):
        phases = [self.phase("gcp_wan_delay")]
        self.assertEqual(live.evaluate(self.records(), phases, 30)["passed"], 1)
        self.assertEqual(live.evaluate(self.records(model=False), phases, 30)["passed"], 0)
        self.assertEqual(live.evaluate(self.records(cause="[CROSS_CLOUD_WAN_DELAY] aws->azure"), phases, 30)["passed"], 0)

    def test_no_samples_or_incomplete_telemetry_never_pass(self):
        phases = [self.phase("gcp_wan_delay")]
        self.assertEqual(live.evaluate([], phases, 30)["passed"], 0)
        records = self.records()
        records[0]["entity_count"] = 0
        self.assertEqual(live.evaluate(records, phases, 30)["passed"], 0)
        self.assertEqual(live.evaluate(self.records()[:1], phases, 30)["passed"], 0)

    def test_recovery_requires_healthy_probes_and_no_alerts(self):
        phases = [self.phase("recovery_after_gcp_wan_delay")]
        records = self.records()
        self.assertEqual(live.evaluate(records, phases, 30)["passed"], 0)
        for record in records:
            record.update(verdict="HEALTHY", model_alert=False, rca_causes=[])
        self.assertEqual(live.evaluate(records, phases, 30)["passed"], 1)
        records[-1]["probe_ok"] = False
        self.assertEqual(live.evaluate(records, phases, 30)["passed"], 0)

    def test_settle_period_excludes_stale_alerts(self):
        records = self.records()
        old = {**records[0], "timestamp": "2026-10-30T00:00:12Z"}
        for record in records:
            record.update(verdict="HEALTHY", model_alert=False)
        result = live.evaluate([old, *records], [self.phase("baseline")], 30)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["results"][0]["samples"], 3)


if __name__ == "__main__":
    unittest.main()
