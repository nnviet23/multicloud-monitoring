#!/usr/bin/env python3
"""Inject bounded WAN faults into the local k3d lab and evaluate the real AI.

Requires kubectl, Docker and a local helper image containing sh, sleep and tc.
The helper owns a watchdog: even if this runner dies, it removes its qdisc.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
FAULTS = {"gcp_wan_delay": ("gcp", 250), "azure_wan_delay": ("azure", 180)}


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=30, **kwargs).stdout


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def qdisc(image, cloud):
    return json.loads(command(["docker", "run", "--rm", "--pull=never", "--network",
                              f"container:k3d-{cloud}-k3d-server-0", image,
                              "tc", "-j", "qdisc", "show", "dev", "eth0"]))


def inject(image, cloud, delay_ms, duration, name):
    original = qdisc(image, cloud)
    # Refuse to overwrite a pre-existing WAN profile that cannot be restored exactly.
    if any(item.get("kind") != "noqueue" for item in original):
        raise RuntimeError(f"{cloud}: existing qdisc must be restored manually before this test: {original}")
    script = ('set -eu; trap \'tc qdisc del dev eth0 root 2>/dev/null || true\' EXIT; '
              'trap \'exit 0\' TERM INT; '
              f'tc qdisc replace dev eth0 root netem delay {delay_ms}ms; '
              f'sleep {duration + 45} & wait $!')
    command(["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
             "--cap-add", "NET_ADMIN", "--network", f"container:k3d-{cloud}-k3d-server-0",
             image, "sh", "-c", script])
    return name, original


def restore(name, image, cloud):
    # docker stop sends TERM to the helper, triggering its cleanup trap.
    result = subprocess.run(["docker", "stop", "--time", "5", name], text=True,
                            capture_output=True, timeout=15)
    current = qdisc(image, cloud)
    if any(item.get("kind") != "noqueue" for item in current):
        # Retry cleanup if the helper's shell did not receive TERM in time.
        command(["docker", "run", "--rm", "--pull=never", "--cap-add", "NET_ADMIN",
                 "--network", f"container:k3d-{cloud}-k3d-server-0", image,
                 "tc", "qdisc", "del", "dev", "eth0", "root"])
        current = qdisc(image, cloud)
    if any(item.get("kind") != "noqueue" for item in current):
        raise RuntimeError(f"Cleanup failed for {cloud}: {current}; docker stop: {result.stderr}")
    return current


def evaluate(records, phases, settle):
    rows = []
    for phase in phases:
        start = datetime.fromisoformat(phase["start"]).timestamp()
        end = datetime.fromisoformat(phase["end"]).timestamp()
        selected = [r for r in records if start + settle <= datetime.fromisoformat(
            r["timestamp"].replace("Z", "+00:00")).timestamp() < end]
        alerts = [r for r in selected if r["verdict"] == "ALERT"]
        model_alerts = [r for r in selected if r.get("model_alert")]
        causes = [cause for r in alerts for cause in r.get("rca_causes", [])]
        fault = phase["id"] in FAULTS
        expected = f"[CROSS_CLOUD_WAN_DELAY] aws->{FAULTS[phase['id']][0]}" if fault else ""
        rca_ok = any(expected in cause for cause in causes) if fault else True
        coverage = len(selected) >= 3 and all(r.get("entity_count", 0) >= 6 for r in selected)
        probes_healthy = bool(selected) and all(r.get("probe_ok") and r.get("probe_ms", 0) < 500
                                                for r in selected)
        # Fault tests require model detection and exact-cloud RCA, not just an SLO guard.
        passed = coverage and (bool(model_alerts) and rca_ok if fault else not alerts and probes_healthy)
        first_alert = next((datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp()
                            for r in records if start <= datetime.fromisoformat(
                                r["timestamp"].replace("Z", "+00:00")).timestamp() < end
                            and r["verdict"] == "ALERT"), None)
        rows.append({**phase, "samples": len(selected), "alerts": len(alerts),
                     "model_alerts": len(model_alerts), "telemetry_complete": coverage,
                     "probes_healthy": probes_healthy,
                     "rca_ok": rca_ok, "rca_causes": list(dict.fromkeys(causes)),
                     "detection_seconds": round(first_alert - start, 1) if first_alert else None,
                     "passed": bool(passed)})
    return {"mode": "live_k3d_fault_injection", "settle_seconds": settle,
            "passed": sum(row["passed"] for row in rows), "total": len(rows), "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", nargs="+", choices=FAULTS, default=list(FAULTS))
    parser.add_argument("--tc-image", default="network-infra-check:ubuntu24.04")
    parser.add_argument("--baseline", type=int, default=90)
    parser.add_argument("--fault", type=int, default=90)
    parser.add_argument("--recovery", type=int, default=120)
    parser.add_argument("--settle", type=int, default=30)
    parser.add_argument("--interval", type=int, default=6)
    parser.add_argument("--users", type=int, default=6)
    parser.add_argument("--output", default="tests/benchmarks/results/live")
    args = parser.parse_args()
    if (args.interval < 1 or args.users < 1 or args.users > 20 or args.settle < 0
            or min(args.baseline, args.fault, args.recovery) < args.settle + 3 * args.interval):
        parser.error("Each phase needs >= settle + 3*interval seconds; users must be 1..20")
    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Avoid replacing a previous run's evidence.
    if (output / "events.json").exists():
        parser.error(f"Use a new --output directory; results already exist in {output}")
    phases, helpers, children = [], {}, []
    cleanup_errors = []
    events_path = output / "events.json"

    def save_events():
        events_path.write_text(json.dumps({"phases": phases, "active_helpers": helpers,
                                          "cleanup_errors": cleanup_errors}, indent=2))

    def phase(name, seconds, detector):
        item = {"id": name, "start": utc_now(), "end": None}
        phases.append(item)
        save_events()
        print(f"{item['start']} {name} ({seconds}s)", flush=True)
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline:
                if detector.poll() is not None:
                    raise RuntimeError(f"Detector exited early with status {detector.returncode}")
                if traffic.poll() is not None:
                    raise RuntimeError(f"Traffic generator exited early: {traffic.returncode}")
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        finally:
            item["end"] = utc_now()
            save_events()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    failure = None
    try:
        for scenario in args.scenarios:
            cloud, _ = FAULTS[scenario]
            command(["docker", "inspect", f"k3d-{cloud}-k3d-server-0"])
            original = qdisc(args.tc_image, cloud)
            if any(item.get("kind") != "noqueue" for item in original):
                raise RuntimeError(f"Existing WAN shaping on {cloud}: {original}")
        command(["kubectl", "--context", "k3d-hub-k3d", "--request-timeout=10s",
                 "-n", "monitoring", "get", "service/prometheus-server", "service/tempo"])
        command(["kubectl", "--context", "k3d-hub-k3d", "--request-timeout=10s",
                 "-n", "monitoring", "wait", "--for=condition=Ready", "pod",
                 "-l", "app.kubernetes.io/name=tempo", "--timeout=10s"])
        with urllib.request.urlopen("http://localhost:8080/tools.descartes.teastore.webui/product?id=7",
                                    timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("TeaStore preflight failed")
        total = args.baseline + len(args.scenarios) * (args.fault + args.recovery)
        env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1"}
        with open(output / "traffic.log", "w") as traffic_log, open(output / "detector.log", "w") as detector_log:
            traffic = subprocess.Popen([sys.executable, "tests/locust/traffic_generator.py",
                                        "--min-users", str(args.users), "--max-users", str(args.users),
                                        "--duration", str(total + 120)], cwd=ROOT, env=env,
                                       stdout=traffic_log, stderr=subprocess.STDOUT)
            children.append(traffic)
            detector = subprocess.Popen([sys.executable, "ai-engine/inference/detector.py", "--interval",
                                         str(args.interval), "--summary-out", str(output / "detector.json")],
                                        cwd=ROOT, env=env, stdout=detector_log, stderr=subprocess.STDOUT)
            children.append(detector)
            # Wait for actual inference, excluding Python imports and port-forward startup.
            deadline = time.monotonic() + 90
            while "Sample #" not in (output / "detector.log").read_text():
                if detector.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Detector failed to start; see detector.log")
                time.sleep(1)
            phase("baseline", args.baseline, detector)
            for scenario in args.scenarios:
                cloud, delay = FAULTS[scenario]
                # Persist the name before docker starts, so interruption still has a cleanup target.
                name = f"ai-chaos-{cloud}-{uuid.uuid4().hex[:8]}"
                helpers[name] = cloud
                save_events()
                try:
                    _, original = inject(args.tc_image, cloud, delay, args.fault, name)
                    actual = qdisc(args.tc_image, cloud)
                    if not any(item.get("kind") == "netem" for item in actual):
                        raise RuntimeError(f"WAN injection did not take effect: {actual}")
                    phase(scenario, args.fault, detector)
                finally:
                    restored = restore(name, args.tc_image, cloud)
                    helpers.pop(name)
                    if phases and phases[-1]["id"] == scenario:
                        phases[-1]["qdisc_before"] = original
                        phases[-1]["qdisc_restored"] = restored
                    save_events()
                phase(f"recovery_after_{scenario}", args.recovery, detector)
    except (Exception, KeyboardInterrupt) as exc:
        failure = str(exc) or "Interrupted"
    finally:
        for name, cloud in list(helpers.items()):
            try:
                restore(name, args.tc_image, cloud)
                helpers.pop(name)
            except Exception as exc:
                cleanup_errors.append(str(exc))
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        save_events()
    records = []
    if (output / "detector.json").exists():
        records = json.loads((output / "detector.json").read_text()).get("records", [])
    report = evaluate(records, phases, args.settle)
    report.update(error=failure, cleanup_errors=cleanup_errors)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    for row in report["results"]:
        print(f"{'PASS' if row['passed'] else 'FAIL'} {row['id']}: "
              f"samples={row['samples']} alerts={row['alerts']} model_alerts={row['model_alerts']} RCA={row['rca_ok']}")
    print(f"Report: {output / 'report.json'}", flush=True)
    if failure:
        print(f"ERROR: {failure}", file=sys.stderr)
    return 0 if not failure and not cleanup_errors and report["total"] and report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
