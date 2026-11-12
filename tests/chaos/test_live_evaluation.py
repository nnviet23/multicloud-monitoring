"""Ensure a live test cannot pass on SLO guards or missing telemetry alone."""
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location("run_live", Path(__file__).with_name("run_live.py"))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveEvaluationTests(unittest.TestCase):
    def phase(self, name):
        return {"id": name, "start": "2026-10-30T00:00:00+00:00", "end": "2026-10-30T00:01:00+00:00"}

    LOCALIZED = "[CROSS_CLOUD_WAN_DELAY] localized_cloud={} (delayed: gcp->aws=259ms; healthy round-trips: azure->aws)"

    def records(self, model=True, cause=None, **overrides):
        cause = cause or self.LOCALIZED.format("gcp")
        return [dict(timestamp=f"2026-10-30T00:00:{second:02d}Z", verdict="ALERT",
                     model_alert=model, rca_causes=[cause], entity_count=6,
                     probe_ok=True, probe_ms=50, **overrides) for second in [36, 42, 48]]

    def test_fault_requires_both_model_and_correct_cloud_rca(self):
        phases = [self.phase("gcp_wan_delay")]
        self.assertEqual(live.evaluate(self.records(), phases, 30)["passed"], 1)
        self.assertEqual(live.evaluate(self.records(model=False), phases, 30)["passed"], 0)
        self.assertEqual(live.evaluate(self.records(cause=self.LOCALIZED.format("azure")), phases, 30)["passed"], 0)
        # A delayed link alone does not name the faulted cloud.
        self.assertEqual(live.evaluate(self.records(cause="[CROSS_CLOUD_WAN_DELAY] aws->gcp (gcp:teastore-recommender) (T_WAN=250ms)"),
                                       phases, 30)["passed"], 0)

    def test_aws_egress_fault_is_scorable(self):
        phases = [self.phase("aws_wan_delay")]
        self.assertEqual(live.evaluate(self.records(cause=self.LOCALIZED.format("aws")), phases, 30)["passed"], 1)

    def test_no_samples_or_incomplete_telemetry_never_pass(self):
        phases = [self.phase("gcp_wan_delay")]
        self.assertEqual(live.evaluate([], phases, 30)["passed"], 0)
        records = self.records()
        records[0]["entity_count"] = 0
        self.assertEqual(live.evaluate(records, phases, 30)["passed"], 0)
        self.assertEqual(live.evaluate(self.records()[:1], phases, 30)["passed"], 0)
        unknown = self.records()
        for record in unknown:
            record.update(verdict="UNKNOWN", telemetry_complete=False)
        self.assertEqual(live.evaluate(unknown, [self.phase("baseline")], 30)["passed"], 0)

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



sys.modules.setdefault("run_live", live)  # run_service_faults imports run_live by name
service_spec = importlib.util.spec_from_file_location("run_service_faults", Path(__file__).with_name("run_service_faults.py"))
service = importlib.util.module_from_spec(service_spec)
service_spec.loader.exec_module(service)


class ServiceFaultDurationTest(unittest.TestCase):
    def test_memory_leak_outlasts_the_ram_floor_window(self):
        # ram_floor_2m_pct is a 120s minimum: a shorter leak can never raise it.
        self.assertGreaterEqual(service.fault_seconds("memory_leak", 90), 120 + 3 * 10)
        self.assertEqual(service.fault_seconds("cpu", 90), 90)
        self.assertEqual(service.fault_seconds("memory_leak", 200), 200)


if __name__ == "__main__":
    unittest.main()
