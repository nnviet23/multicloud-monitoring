#!/usr/bin/env python3
"""Bounded real JVM CPU, MariaDB lock, and WebUI outage tests in the k3d lab."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import ipaddress

from run_live import ROOT, command, utc_now


def kubectl(cloud, *args):
    return ["kubectl", "--context", f"k3d-{cloud}-k3d", "--request-timeout=10s", "-n", "teastore", *args]


def sql_command(sql, timeout=150):
    return kubectl("azure", "exec", "deploy/teastore-db", "--", "sh", "-c",
                   'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec timeout "$2" mysql -uroot -N --unbuffered -e "$1"',
                   "sh", sql, str(timeout))


class Fault:
    JVM_TARGETS = {
        "cpu": ("gcp", "deploy/teastore-recommender"),
        "memory_leak": ("azure", "deploy/teastore-persistence"),
    }

    def __init__(self, name, duration):
        self.name, self.duration = name, duration
        self.pid = self.connection = self.original_replicas = self.watchdog = self.process = None
        self.evidence = {}

    def prepare(self):
        if self.name in self.JVM_TARGETS:
            cloud, deploy = self.JVM_TARGETS[self.name]
            source = (ROOT / "tests/chaos/java/FaultAgent.java").read_text()
            command(kubectl(cloud, "exec", "-i", deploy, "--", "sh", "-c",
                            "mkdir -p /tmp/ai-chaos; cat > /tmp/ai-chaos/FaultAgent.java"), input=source)
            command(kubectl(cloud, "exec", deploy, "--", "sh", "-c",
                            'cd /tmp/ai-chaos && env -u JAVA_TOOL_OPTIONS javac -J-Xmx64m --add-modules jdk.attach FaultAgent.java && '
                            'printf "Agent-Class: FaultAgent\\n" > MANIFEST.MF && env -u JAVA_TOOL_OPTIONS jar -J-Xmx32m cfm fault.jar MANIFEST.MF FaultAgent.class'))
            processes = command(kubectl(cloud, "exec", deploy, "--", "ps", "-eo", "pid,comm,args"))
            self.pid = next(line.split()[0] for line in processes.splitlines()
                            if len(line.split()) > 2 and line.split()[1] == "java" and "org.apache.catalina.startup.Bootstrap" in line)

    def attach(self, action):
        cloud, deploy = self.JVM_TARGETS[self.name]
        return command(kubectl(cloud, "exec", deploy, "--", "env", "-u", "JAVA_TOOL_OPTIONS", "java", "-Xmx32m", "--add-modules", "jdk.attach",
                               "-cp", "/tmp/ai-chaos", "FaultAgent", self.pid, "/tmp/ai-chaos/fault.jar", str(action)))

    def start(self):
        if self.name == "cpu":
            self.attach(self.duration)
        elif self.name == "memory_leak":
            self.attach(f"memory:{self.duration}")
            self.evidence = {"jvm_memory_agent_attached": True, "target": "azure:teastore-persistence"}
        elif self.name == "http_5xx":
            url = "http://localhost:8080/tools.descartes.teastore.webui/cartAction?addToCart=&productid=abc"
            status = 0
            try:
                urllib.request.urlopen(urllib.request.Request(url, data=b"", method="POST"), timeout=5)
            except urllib.error.HTTPError as err:
                status = err.code
            if status != 500:
                raise RuntimeError(f"Expected HTTP 500 from Fault endpoint, got {status}")
            self.evidence = {"http_500_verified": True, "status_code": 500}
            script = (
                "import time, urllib.request, urllib.error\n"
                f"url = {url!r}\n"
                f"deadline = time.monotonic() + {self.duration + 10}\n"
                "while time.monotonic() < deadline:\n"
                "    try:\n"
                "        urllib.request.urlopen(urllib.request.Request(url, data=b'', method='POST'), timeout=3)\n"
                "    except Exception:\n"
                "        pass\n"
                "    time.sleep(0.35)\n"
            )
            self.process = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif self.name == "db_lock":
            pulses = " ".join(
                "LOCK TABLES teadb.PERSISTENCEPRODUCT WRITE, teadb.PERSISTENCECATEGORY WRITE; "
                "DO SLEEP(0.35); UNLOCK TABLES; DO SLEEP(0.02);"
                for _ in range(int((self.duration + 15) / 0.37))
            )
            sql = ("SET autocommit=0; SET SESSION query_cache_wlock_invalidate=ON; RESET QUERY CACHE; "
                   "LOCK TABLES teadb.PERSISTENCEPRODUCT WRITE, teadb.PERSISTENCECATEGORY WRITE; "
                   "SELECT CONCAT('FAULT_STARTED ',CONNECTION_ID()); "
                   f"DO SLEEP(3.5); UNLOCK TABLES; {pulses} COMMIT; UNLOCK TABLES;")
            self.process = subprocess.Popen(sql_command(sql, self.duration + 25), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            selector = selectors.DefaultSelector()
            try:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=15):
                    raise RuntimeError("MariaDB lock did not start within 15s")
                line = self.process.stdout.readline().strip()
                if not line.startswith("FAULT_STARTED "):
                    raise RuntimeError(f"MariaDB lock failed to start: {line}")
                self.connection = int(line.split()[1])
                verification = subprocess.run(sql_command("SELECT COUNT(*) FROM teadb.PERSISTENCEPRODUCT", 2),
                                              capture_output=True, text=True, timeout=10)
                if verification.returncode != 124:
                    raise RuntimeError("DB lock did not block an independent SQL reader; refusing to score a fictitious fault")
                self.evidence = {"sql_lock_verified": True, "independent_reader_exit_code": 124}
                # TeaStore serves warmed catalog reads from its JPA cache. Evict
                # that cache so test requests actually exercise the locked DB.
                # This endpoint evicts local cache entries; it does not delete rows.
                node = command(kubectl("azure", "get", "nodes", "-o",
                    "jsonpath={.items[0].status.addresses[?(@.type==\"InternalIP\")].address}")).strip()
                node = str(ipaddress.ip_address(node))
                request = urllib.request.Request(
                    f"http://{node}:31111/tools.descartes.teastore.persistence/rest/cache/cache", method="DELETE")
                with urllib.request.urlopen(request, timeout=5) as response:
                    if response.status != 200 or b"cleared" not in response.read():
                        raise RuntimeError("TeaStore catalog cache eviction failed")
            finally:
                selector.close()
        else:
            deployment = json.loads(command(kubectl("aws", "get", "deploy/teastore-webui", "-o", "json")))
            self.original_replicas = deployment["spec"].get("replicas", 1)
            restore = kubectl("aws", "scale", "deploy/teastore-webui", f"--replicas={self.original_replicas}")
            # Independent watchdog restores replicas if the runner is killed.
            script = "import time,subprocess;time.sleep(" + str(self.duration + 30) + ");subprocess.run(" + repr(restore) + ",check=False)"
            self.watchdog = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, start_new_session=True)
            command(kubectl("aws", "scale", "deploy/teastore-webui", "--replicas=0"))

    def close(self):
        if self.name in self.JVM_TARGETS and self.pid:
            self.attach("stop")
        elif self.name == "db_lock" and self.connection:
            result = subprocess.run(sql_command(f"KILL {self.connection}"), capture_output=True, text=True, timeout=15)
            if result.returncode and "Unknown thread id" not in result.stderr:
                raise RuntimeError(result.stderr)
        elif self.original_replicas is not None:
            command(kubectl("aws", "scale", "deploy/teastore-webui", f"--replicas={self.original_replicas}"))
            if self.watchdog:
                self.watchdog.terminate()
                self.watchdog.wait(timeout=5)
            command(kubectl("aws", "rollout", "status", "deploy/teastore-webui", "--timeout=60s"))
            deadline = time.monotonic() + 60
            ok_streak = 0
            while time.monotonic() < deadline and ok_streak < 2:
                try:
                    with urllib.request.urlopen("http://localhost:8080/tools.descartes.teastore.webui/product?id=7", timeout=4) as resp:
                        if 200 <= resp.status < 400:
                            ok_streak += 1
                        else:
                            ok_streak = 0
                except Exception:
                    ok_streak = 0
                time.sleep(2)
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.communicate(timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", nargs="+",
                        choices=["cpu", "db_lock", "memory_leak", "http_5xx", "webui_outage"],
                        default=["cpu", "db_lock", "memory_leak", "http_5xx", "webui_outage"])
    parser.add_argument("--fault", type=int, default=60)
    parser.add_argument("--recovery", type=int, default=120)
    parser.add_argument("--users", type=int, default=6)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 30 <= args.fault <= 120 or args.recovery < 90 or not 1 <= args.users <= 20:
        parser.error("fault must be 30..120s, recovery >=90s, users 1..20")
    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "events.json").exists():
        parser.error("Choose a new output directory")
    phases, children, cleanup_errors = [], [], []
    active = None

    def save():
        (output / "events.json").write_text(json.dumps({"phases": phases, "cleanup_errors": cleanup_errors}, indent=2))

    def phase(name, duration, evidence=None):
        event = {"id": name, "start": utc_now(), "end": None}
        event.update(evidence or {})
        phases.append(event)
        save()
        print(f"{event['start']} {name} ({duration}s)", flush=True)
        try:
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("Detector or traffic exited prematurely; inspect logs")
                time.sleep(1)
        finally:
            event["end"] = utc_now()
            save()

    def interrupted(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    failure = None
    try:
        # Compile the agent before the baseline so compilation is excluded from measurement.
        prepared = {name: Fault(name, args.fault) for name in args.scenarios}
        for fault in prepared.values():
            fault.prepare()
        total = 60 + len(args.scenarios) * (args.fault + args.recovery)
        env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1"}
        with (output / "detector.log").open("w") as dl, (output / "traffic.log").open("w") as tl:
            children.append(subprocess.Popen([sys.executable, "tests/locust/traffic_generator.py", "--duration", str(total + 180),
                "--min-users", str(args.users), "--max-users", str(args.users)], cwd=ROOT, env=env, stdout=tl, stderr=subprocess.STDOUT))
            children.append(subprocess.Popen([sys.executable, "ai-engine/inference/detector.py", "--interval", "6",
                "--summary-out", str(output / "detector.json")], cwd=ROOT, env=env, stdout=dl, stderr=subprocess.STDOUT))
            deadline = time.monotonic() + 90
            while "Sample #" not in (output / "detector.log").read_text():
                if children[-1].poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Detector startup failed")
                time.sleep(1)
            phase("baseline", 60)
            for name in args.scenarios:
                active = prepared[name]
                active.start()
                try:
                    phase(name, args.fault, active.evidence)
                finally:
                    active.close()
                    active = None
                phase("recovery_after_" + name, args.recovery)
    except (Exception, KeyboardInterrupt) as exc:
        failure = str(exc) or "Interrupted"
    finally:
        if active:
            try:
                active.close()
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
        save()
    records = json.loads((output / "detector.json").read_text()).get("records", []) if (output / "detector.json").exists() else []
    from datetime import datetime
    def epoch(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    rows = []
    for event in phases:
        selected = [r for r in records if epoch(event["start"]) + 30 <= epoch(r["timestamp"]) < epoch(event["end"])]
        alerts = [r for r in selected if r["verdict"] == "ALERT"]
        healthy = [r for r in selected if r["verdict"] == "HEALTHY" and r["probe_ok"]]
        fault = event["id"] in args.scenarios
        complete = len(selected) >= 3 and all(r.get("telemetry_complete", False) for r in selected)
        passed = complete and (bool(alerts) if fault else len(healthy) == len(selected))
        causes = list(dict.fromkeys(cause for r in alerts for cause in r.get("rca_causes", [])))
        if event["id"] == "cpu":
            passed = passed and any(r.get("model_alert") for r in selected) and any(
                "gcp:teastore-recommender" in cause and ("cpu" in cause.lower()) for cause in causes)
        if event["id"] == "db_lock":
            incident = [r for r in records if epoch(event["start"]) <= epoch(r["timestamp"]) < epoch(event["end"]) + 30]
            passed = passed and any(r.get("model_alert") for r in selected) and any(
                "DATABASE_BOTTLENECK" in c for r in incident for c in r.get("rca_causes", []))
        if event["id"] == "memory_leak":
            passed = passed and any(r.get("model_alert") for r in selected) and any(
                "MEMORY_LEAK_GC_STALL" in c and "azure:teastore-persistence" in c for c in causes)
        if event["id"] == "http_5xx":
            passed = passed and any(r.get("model_alert") for r in selected) and any(
                "aws:teastore-webui" in c and "error_rate_5xx" in c for c in causes)
        if event["id"] == "webui_outage":
            # Missing JVM telemetry is expected for the deliberately stopped
            # service. Availability must still alert via independent HTTP probes.
            passed = len(selected) >= 3 and bool(alerts) and any(not r["probe_ok"] for r in selected)
        rows.append({**event, "samples": len(selected), "alerts": len(alerts), "model_alerts": sum(bool(r.get("model_alert")) for r in selected),
                     "rca_causes": causes, "passed": bool(passed)})
    report = {"mode": "real_service_faults", "results": rows, "error": failure, "cleanup_errors": cleanup_errors}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if rows and all(row["passed"] for row in rows) and not failure and not cleanup_errors else 1


if __name__ == "__main__":
    sys.exit(main())
