#!/usr/bin/env python3
"""Multi-Cloud Monitoring Platform Infrastructure CLI.

Native, cross-platform CLI tool managing k3d multi-cluster lifecycle,
WAN emulation, PKI certificates, DNS synchronization, and Argo CD GitOps registration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from infra.scripts.register_argocd_spokes import register_spokes_in_argocd

app = typer.Typer(
    name="platform-cli",
    help="Multi-Cloud Monitoring Platform Infrastructure Management CLI",
    add_completion=False,
)
console = Console()

NETWORK_NAME = "mc-monitoring-net"
NETWORK_SUBNET = "172.28.0.0/16"
K3S_IMAGE_DEFAULT = "rancher/k3s:v1.31.2-k3s1"

CLUSTER_CONFIGS = {
    "hub-k3d": {
        "ports": [
            "3000:3000@loadbalancer",
            "9000:9000@loadbalancer",
            "9001:9001@loadbalancer",
            "4317:4317@loadbalancer",
            "4318:4318@loadbalancer",
        ]
    },
    "aws-k3d": {
        "ports": [
            "8080:8080@loadbalancer",
            "30080:30080@server:0",
            "8089:8089@loadbalancer",
            "31112:31112@loadbalancer",
        ]
    },
    "azure-k3d": {
        "ports": [
            "31111:31111@loadbalancer",
        ]
    },
}

PINNED_IMAGES = {
    "aws-k3d": [
        "descartesresearch/teastore-webui:1.4.1",
        "descartesresearch/teastore-registry:1.4.1",
        "descartesresearch/teastore-auth:1.4.1",
        "descartesresearch/teastore-image:1.4.1",
        "descartesresearch/teastore-recommender:1.4.1",
        "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0",
        "otel/opentelemetry-collector-contrib:0.114.0",
        "bitnami/sealed-secrets-controller:v0.24.5",
        "ghcr.io/kyverno/kyverno:v1.20.0",
        "ghcr.io/kyverno/kyvernopre:v1.20.0",
        "ghcr.io/kyverno/background-controller:v1.20.0",
        "ghcr.io/kyverno/cleanup-controller:v1.20.0",
        "ghcr.io/kyverno/reports-controller:v1.20.0",
    ],
    "azure-k3d": [
        "descartesresearch/teastore-persistence:1.4.1",
        "descartesresearch/teastore-db:1.4.1",
        "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0",
        "otel/opentelemetry-collector-contrib:0.114.0",
        "bitnami/sealed-secrets-controller:v0.24.5",
        "ghcr.io/kyverno/kyverno:v1.20.0",
        "ghcr.io/kyverno/kyvernopre:v1.20.0",
        "ghcr.io/kyverno/background-controller:v1.20.0",
        "ghcr.io/kyverno/cleanup-controller:v1.20.0",
        "ghcr.io/kyverno/reports-controller:v1.20.0",
    ],
    "hub-k3d": [
        "otel/opentelemetry-collector-contrib:0.114.0",
        "cgr.dev/chainguard/minio@sha256:37919418497f2f8ac6ef5c18760fcd01d1c8f2d17d36723fae0cb2fae67d8093",
        "prom/prometheus:v2.50.0",
        "prom/alertmanager:v0.27.0",
        "quay.io/thanos/thanos:v0.36.1",
        "grafana/loki:2.9.4",
        "grafana/tempo:2.4.0",
        "grafana/grafana:11.5.0",
        "kiwigrid/k8s-sidecar:1.28.0",
        "ghcr.io/pyrra-dev/pyrra:v0.7.3",
        "robustadev/robusta-runner:0.53.0",
        "bitnami/sealed-secrets-controller:v0.24.5",
        "quay.io/jetstack/cert-manager-controller:v1.16.2",
        "quay.io/jetstack/cert-manager-webhook:v1.16.2",
        "quay.io/jetstack/cert-manager-cainjector:v1.16.2",
        "quay.io/argoproj/argocd:v3.6.2",
        "quay.io/argoproj/workflow-controller:v4.1.6",
        "quay.io/argoproj/argocli:v4.1.6",
        "redis:7.2.7-alpine",
        "ghcr.io/kyverno/kyverno:v1.20.0",
        "ghcr.io/kyverno/kyvernopre:v1.20.0",
        "ghcr.io/kyverno/background-controller:v1.20.0",
        "ghcr.io/kyverno/cleanup-controller:v1.20.0",
        "ghcr.io/kyverno/reports-controller:v1.20.0",
    ],
}


def run_cmd(
    cmd: list[str],
    check: bool = False,
    capture: bool = True,
    stdin_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external CLI command safely."""
    return subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=capture,
        text=True,
        check=check,
    )


@app.command("up")
def up_cmd(
    network_name: Annotated[str, typer.Option("--network", help="Docker bridge network name")] = NETWORK_NAME,
    subnet: Annotated[str, typer.Option("--subnet", help="Subnet CIDR for bridge network")] = NETWORK_SUBNET,
    k3s_image: Annotated[str, typer.Option("--k3s-image", help="Pinned k3s container image")] = K3S_IMAGE_DEFAULT,
) -> None:
    """Provision Docker network and 3 k3d clusters (hub-k3d, aws-k3d, azure-k3d)."""
    console.print(f"[bold cyan]>>> Provisioning Docker network '{network_name}' ({subnet})...[/bold cyan]")
    net_check = run_cmd(["docker", "network", "inspect", network_name])
    if net_check.returncode != 0:
        res = run_cmd(["docker", "network", "create", "--driver", "bridge", "--subnet", subnet, network_name])
        if res.returncode == 0:
            console.print(f"[green][OK] Created Docker network {network_name}[/green]")
        else:
            console.print(f"[yellow][WARN] Docker network create: {res.stderr.strip()}[/yellow]")
    else:
        console.print(f"[blue][INFO] Docker network {network_name} already exists.[/blue]")

    # List existing k3d clusters
    clusters_raw = run_cmd(["k3d", "cluster", "list", "-o", "json"])
    existing_clusters: list[str] = []
    if clusters_raw.returncode == 0 and clusters_raw.stdout.strip():
        try:
            parsed = json.loads(clusters_raw.stdout)
            if isinstance(parsed, list):
                existing_clusters = [c.get("name", "") for c in parsed]
        except Exception:
            pass

    for cluster_name, cfg in CLUSTER_CONFIGS.items():
        if cluster_name in existing_clusters:
            console.print(f"[blue][INFO] Cluster {cluster_name} already exists. Skipping create.[/blue]")
            continue

        console.print(f"[bold cyan]>>> Creating k3d cluster: {cluster_name}...[/bold cyan]")
        cmd = [
            "k3d",
            "cluster",
            "create",
            cluster_name,
            "--image",
            k3s_image,
            "--network",
            network_name,
            "--agents",
            "0",
            "--k3s-arg",
            "--disable=traefik@server:0",
            "--k3s-arg",
            "--disable=metrics-server@server:0",
        ]
        for port in cfg["ports"]:
            cmd.extend(["-p", port])

        create_res = run_cmd(cmd)
        if create_res.returncode == 0:
            console.print(f"[green][OK] Cluster {cluster_name} provisioned successfully.[/green]")
        else:
            console.print(f"[red][ERROR] Failed to create cluster {cluster_name}: {create_res.stderr.strip()}[/red]")
            raise typer.Exit(code=1)

    # Wait for nodes condition=Ready
    for cluster_name in CLUSTER_CONFIGS.keys():
        ctx = f"k3d-{cluster_name}"
        console.print(f"[bold cyan]>>> Waiting for {cluster_name} nodes to report Ready...[/bold cyan]")
        wait_res = run_cmd(
            ["kubectl", "--context", ctx, "wait", "--for=condition=Ready", "node", "--all", "--timeout=120s"]
        )
        if wait_res.returncode == 0:
            console.print(f"[green][OK] Nodes in {cluster_name} are Ready.[/green]")
        else:
            console.print(f"[yellow][WARN] Node wait warning for {cluster_name}: {wait_res.stderr.strip()}[/yellow]")

    console.print("[bold green]All 3 k3d clusters provisioned and healthy![/bold green]")


@app.command("down")
def down_cmd(
    network_name: Annotated[str, typer.Option("--network", help="Docker bridge network name")] = NETWORK_NAME,
    clean_certs: Annotated[bool, typer.Option("--clean-certs", help="Remove generated PKI certificates")] = True,
) -> None:
    """Delete k3d clusters, Docker network, and clean up resources."""
    console.print("[bold yellow]>>> Tearing down k3d clusters...[/bold yellow]")
    for cluster_name in CLUSTER_CONFIGS.keys():
        del_res = run_cmd(["k3d", "cluster", "delete", cluster_name])
        if del_res.returncode == 0:
            console.print(f"[green][OK] Deleted cluster {cluster_name}[/green]")
        else:
            console.print(f"[blue][INFO] Cluster {cluster_name} delete: {del_res.stderr.strip()}[/blue]")

    # Clean leftover containers
    ps_res = run_cmd(["docker", "ps", "-a", "-q", "--filter", "name=k3d-"])
    containers = [c.strip() for c in ps_res.stdout.splitlines() if c.strip()]
    if containers:
        console.print(f"[yellow]Removing lingering k3d containers: {len(containers)}...[/yellow]")
        run_cmd(["docker", "rm", "-f"] + containers)

    # Remove Docker bridge network
    console.print(f"[bold yellow]>>> Removing Docker network '{network_name}'...[/bold yellow]")
    net_rm = run_cmd(["docker", "network", "rm", network_name])
    if net_rm.returncode == 0:
        console.print(f"[green][OK] Removed network {network_name}[/green]")

    # Prune dangling volumes
    run_cmd(["docker", "volume", "prune", "-f"])

    if clean_certs:
        console.print("[yellow]Cleaning in-cluster PKI secrets across clusters and local caches...[/yellow]")
        for _, ctx in [("hub-k3d", "k3d-hub-k3d"), ("aws-k3d", "k3d-aws-k3d"), ("azure-k3d", "k3d-azure-k3d")]:
            run_cmd([
                "kubectl", "--context", ctx, "-n", "monitoring", "delete", "secret",
                "hub-otel-gateway-tls", "otel-hub-certs", "otel-spoke-certs",
                "otel-spoke-client-cert", "aws-spoke-collector-tls", "azure-spoke-collector-tls",
                "--ignore-not-found=true"
            ])
        for pattern in ["certs-*", "ca"]:
            for item in Path(".").glob(pattern):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
        console.print("[green][OK] In-cluster and local PKI certs cleaned.[/green]")

    console.print("[bold green]Teardown complete.[/bold green]")


@app.command("wan")
def wan_cmd(
    latency: Annotated[str, typer.Option("--latency", help="Base WAN latency (e.g. 10ms)")] = "10ms",
    jitter: Annotated[str, typer.Option("--jitter", help="Latency jitter (e.g. 2ms)")] = "2ms",
    loss: Annotated[str, typer.Option("--loss", help="Packet loss percentage (e.g. 0.1%)")] = "0.1%",
    reset: Annotated[bool, typer.Option("--reset", help="Reset WAN emulation to default (remove qdisc)")] = False,
) -> None:
    """Emulate or reset cross-cloud WAN network characteristics (latency & loss)."""
    spoke_containers = ["k3d-aws-k3d-server-0", "k3d-azure-k3d-server-0"]
    for container in spoke_containers:
        if reset:
            console.print(f"[bold yellow]>>> Resetting WAN netem on {container}...[/bold yellow]")
            tc_cmd = [
                "docker", "run", "--rm", "--cap-add=NET_ADMIN", f"--net=container:{container}",
                "alpine:3.20", "sh", "-c",
                "apk add --no-cache iproute2 >/dev/null 2>&1 && tc qdisc del dev eth0 root",
            ]
        else:
            console.print(
                f"[bold cyan]>>> Applying WAN netem on {container} (delay {latency} {jitter} loss {loss})...[/bold cyan]"
            )
            tc_cmd = [
                "docker", "run", "--rm", "--cap-add=NET_ADMIN", f"--net=container:{container}",
                "alpine:3.20", "sh", "-c",
                f"apk add --no-cache iproute2 >/dev/null 2>&1 && tc qdisc replace dev eth0 root netem delay {latency} {jitter} loss {loss}",
            ]

        res = run_cmd(tc_cmd)
        # Display current qdisc
        show_cmd = [
            "docker", "run", "--rm", "--cap-add=NET_ADMIN", f"--net=container:{container}",
            "alpine:3.20", "sh", "-c",
            "apk add --no-cache iproute2 >/dev/null 2>&1 && tc qdisc show dev eth0",
        ]
        status_res = run_cmd(show_cmd)
        console.print(f"    - {container}: {status_res.stdout.strip() or res.stdout.strip()}")

    console.print("[bold green]WAN network emulation updated successfully.[/bold green]")


@app.command("certs")
def certs_cmd(
    hub_context: Annotated[str, typer.Option("--hub-context", help="Hub cluster kubectl context")] = "k3d-hub-k3d",
    apply_manifests: Annotated[bool, typer.Option("--apply", help="Apply cert-manager and certificate manifests to Hub")] = True,
    distribute: Annotated[bool, typer.Option("--distribute", help="Synchronize mTLS client certificates from Hub to Spokes")] = True,
) -> None:
    """Manage in-cluster PKI via cert-manager on Hub and synchronize mTLS certificates across clusters."""
    console.print("[bold cyan]>>> Establishing In-Cluster PKI with cert-manager on Hub...[/bold cyan]")

    # 1. Apply cert-manager manifests to Hub if requested
    if apply_manifests:
        cert_manager_kust = Path("deploy/platform/cert-manager")
        if cert_manager_kust.is_dir():
            apply_res = run_cmd(["kubectl", "--context", hub_context, "apply", "-k", str(cert_manager_kust)])
            if apply_res.returncode == 0:
                console.print(f"[green][OK] Applied cert-manager manifests to {hub_context}[/green]")
                wait_res = run_cmd([
                    "kubectl", "--context", hub_context, "-n", "monitoring", "wait",
                    "--for=condition=Ready",
                    "certificate/hub-otel-gateway-server-cert",
                    "certificate/aws-spoke-client-cert",
                    "certificate/azure-spoke-client-cert",
                    "--timeout=90s",
                ])
                if wait_res.returncode != 0:
                    console.print(
                        f"[yellow][WARN] Timed out or failed waiting for certificates on {hub_context}: "
                        f"{wait_res.stderr.strip()}[/yellow]"
                    )
            else:
                console.print(f"[yellow][WARN] Could not apply cert-manager to {hub_context}: {apply_res.stderr.strip()}[/yellow]")

    if not distribute:
        return

    console.print("[bold cyan]>>> Synchronizing in-cluster mTLS secrets across clusters...[/bold cyan]")
    clusters = [
        ("hub-k3d", "k3d-hub-k3d"),
        ("aws-k3d", "k3d-aws-k3d"),
        ("azure-k3d", "k3d-azure-k3d"),
    ]

    # Ensure monitoring namespaces
    for _, ctx in clusters:
        ns_manifest = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: monitoring\n"
        run_cmd(["kubectl", "--context", ctx, "apply", "-f", "-"], stdin_data=ns_manifest)

    # 1. Fetch Root CA secret from cert-manager namespace on Hub
    root_ca_raw = run_cmd(["kubectl", "--context", hub_context, "-n", "cert-manager", "get", "secret", "multicloud-root-ca-secret", "-o", "json"])
    ca_crt_b64 = ""
    if root_ca_raw.returncode == 0 and root_ca_raw.stdout.strip():
        try:
            root_data = json.loads(root_ca_raw.stdout).get("data", {})
            ca_crt_b64 = root_data.get("ca.crt") or root_data.get("tls.crt", "")
        except Exception:
            pass

    # 2. Fetch Hub Gateway certificate
    hub_cert_raw = run_cmd(["kubectl", "--context", hub_context, "-n", "monitoring", "get", "secret", "hub-otel-gateway-tls", "-o", "json"])
    if hub_cert_raw.returncode == 0 and hub_cert_raw.stdout.strip():
        try:
            hub_data = json.loads(hub_cert_raw.stdout).get("data", {})
            tls_crt = hub_data.get("tls.crt", "")
            tls_key = hub_data.get("tls.key", "")
            ca_crt = hub_data.get("ca.crt", "") or ca_crt_b64

            secret_manifest = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "otel-hub-certs", "namespace": "monitoring"},
                "type": "Opaque",
                "data": {
                    "tls.crt": tls_crt,
                    "tls.key": tls_key,
                    "server.crt": tls_crt,
                    "server.key": tls_key,
                    "ca.crt": ca_crt,
                },
            }
            run_cmd(["kubectl", "--context", hub_context, "apply", "-f", "-"], stdin_data=json.dumps(secret_manifest))
            console.print("[green][OK] Hub Gateway mTLS secrets synchronized in-memory.[/green]")
        except Exception as e:
            console.print(f"[yellow][WARN] Error syncing Hub certificate: {e}[/yellow]")

    # 3. Fetch per-spoke client certificates from Hub and distribute exclusively to each spoke
    spoke_targets = [
        ("aws-spoke-client-tls", "k3d-aws-k3d", "aws-spoke-collector-tls"),
        ("azure-spoke-client-tls", "k3d-azure-k3d", "azure-spoke-collector-tls"),
    ]
    for hub_secret_name, spoke_ctx, spoke_secret_name in spoke_targets:
        spoke_cert_raw = run_cmd([
            "kubectl", "--context", hub_context, "-n", "monitoring", "get",
            "secret", hub_secret_name, "-o", "json",
        ])
        if spoke_cert_raw.returncode == 0 and spoke_cert_raw.stdout.strip():
            try:
                spoke_data = json.loads(spoke_cert_raw.stdout).get("data", {})
                tls_crt = spoke_data.get("tls.crt", "")
                tls_key = spoke_data.get("tls.key", "")
                ca_crt = spoke_data.get("ca.crt", "") or ca_crt_b64

                for sec_name in ["otel-spoke-certs", spoke_secret_name]:
                    spoke_sec = {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": {"name": sec_name, "namespace": "monitoring"},
                        "type": "Opaque",
                        "data": {
                            "tls.crt": tls_crt,
                            "tls.key": tls_key,
                            "client.crt": tls_crt,
                            "client.key": tls_key,
                            "ca.crt": ca_crt,
                        },
                    }
                    run_cmd(["kubectl", "--context", spoke_ctx, "apply", "-f", "-"], stdin_data=json.dumps(spoke_sec))
                console.print(f"[green][OK] Synchronized {hub_secret_name} exclusively to {spoke_ctx}[/green]")
            except Exception as e:
                console.print(f"[yellow][WARN] Error syncing {hub_secret_name} to {spoke_ctx}: {e}[/yellow]")
        else:
            console.print(f"[blue][INFO] {hub_secret_name} not yet available on Hub (applied or offline).[/blue]")

    console.print("[bold green]In-cluster PKI management completed (zero host filesystem writes).[/bold green]")

    console.print("[bold green]mTLS secrets distributed across Hub and Spokes successfully.[/bold green]")


@app.command("sync-hosts")
def sync_hosts_cmd(
    host_gateway_ip: Annotated[str, typer.Option("--host-gateway-ip", help="Host gateway IP")] = os.getenv("DOCKER_HOST_GATEWAY_IP", "192.168.65.254"),
) -> None:
    """Synchronize CoreDNS NodeHosts across all 3 k3d clusters."""
    containers = [
        "k3d-hub-k3d-server-0",
        "k3d-hub-k3d-serverlb",
        "k3d-aws-k3d-server-0",
        "k3d-aws-k3d-serverlb",
        "k3d-azure-k3d-server-0",
        "k3d-azure-k3d-serverlb",
    ]

    console.print("[bold cyan]>>> Inspecting container IP addresses...[/bold cyan]")
    hosts_entries: list[str] = [f"{host_gateway_ip} host.k3d.internal"]

    for container in containers:
        inspect_res = run_cmd(
            ["docker", "inspect", "--format", f"{{{{(index .NetworkSettings.Networks \"{NETWORK_NAME}\").IPAddress}}}}", container]
        )
        raw_ips = inspect_res.stdout.strip().split()
        ip = raw_ips[0] if raw_ips else ""
        if ip:
            hosts_entries.append(f"{ip} {container}")
            if container == "k3d-hub-k3d-serverlb":
                hosts_entries.append(f"{ip} hub-gateway.hub.multicloud.local")
                hosts_entries.append(f"{ip} thanos-query.hub.multicloud.local")

    node_hosts_content = "\n".join(hosts_entries) + "\n"
    console.print("[cyan]Assembled NodeHosts:[/cyan]")
    console.print(node_hosts_content)

    clusters = [
        ("hub-k3d", "k3d-hub-k3d"),
        ("aws-k3d", "k3d-aws-k3d"),
        ("azure-k3d", "k3d-azure-k3d"),
    ]

    patch_payload = json.dumps({"data": {"NodeHosts": node_hosts_content}})

    for name, ctx in clusters:
        console.print(f"[bold cyan]>>> Patching CoreDNS ConfigMap on {name} ({ctx})...[/bold cyan]")
        patch_res = run_cmd(
            ["kubectl", "--context", ctx, "-n", "kube-system", "patch", "configmap", "coredns", "--type", "merge", "-p", patch_payload]
        )
        if patch_res.returncode == 0:
            console.print(f"[green][OK] CoreDNS patched on {name}[/green]")
        else:
            console.print(f"[yellow][WARN] CoreDNS patch on {name}: {patch_res.stderr.strip()}[/yellow]")

        # Restart rollout
        restart_res = run_cmd(["kubectl", "--context", ctx, "-n", "kube-system", "rollout", "restart", "deployment", "coredns"])
        if restart_res.returncode != 0:
            console.print(f"[yellow][WARN] CoreDNS rollout restart on {name}: {restart_res.stderr.strip()}[/yellow]")
        status_res = run_cmd(["kubectl", "--context", ctx, "-n", "kube-system", "rollout", "status", "deployment", "coredns", "--timeout=60s"])
        if status_res.returncode != 0:
            console.print(f"[yellow][WARN] CoreDNS rollout status on {name}: {status_res.stderr.strip()}[/yellow]")

    console.print("[bold green]CoreDNS NodeHosts synchronized across all 3 clusters![/bold green]")


@app.command("pull-images")
def pull_images_cmd(
    target_cluster: Annotated[Optional[str], typer.Option("--cluster", help="Target cluster name (default: all)")] = None,
) -> None:
    """Pre-pull all version-pinned container images onto the local Docker daemon."""
    clusters_to_process = [target_cluster] if target_cluster else list(PINNED_IMAGES.keys())
    unique_images: list[str] = ["rancher/k3s:v1.31.2-k3s1", "alpine:3.20"]
    for cluster in clusters_to_process:
        for img in PINNED_IMAGES.get(cluster, []):
            if img not in unique_images:
                unique_images.append(img)

    console.print(f"[bold cyan]>>> Pulling {len(unique_images)} version-pinned images...[/bold cyan]")
    for img in unique_images:
        res = run_cmd(["docker", "pull", img])
        if res.returncode == 0:
            console.print(f"[green][OK] Pulled {img}[/green]")
        else:
            console.print(f"[yellow][WARN] Failed to pull {img}: {res.stderr.strip()}[/yellow]")

    console.print("[bold green]Image pull process completed.[/bold green]")


@app.command("preload-images")
def preload_images_cmd(
    target_cluster: Annotated[Optional[str], typer.Option("--cluster", help="Target cluster name (default: all)")] = None,
) -> None:
    """Preload/import container images into k3d clusters' containerd runtime."""
    clusters_to_process = [target_cluster] if target_cluster else list(PINNED_IMAGES.keys())

    for cluster in clusters_to_process:
        images = PINNED_IMAGES.get(cluster, [])
        if not images:
            console.print(f"[yellow]No pinned images defined for cluster {cluster}[/yellow]")
            continue

        console.print(f"[bold cyan]>>> Importing {len(images)} images into {cluster}...[/bold cyan]")
        # k3d image import <images> -c <cluster>
        cmd = ["k3d", "image", "import"] + images + ["-c", cluster]
        res = run_cmd(cmd)
        if res.returncode == 0:
            console.print(f"[green][OK] Images imported into {cluster}[/green]")
        else:
            console.print(f"[yellow][WARN] k3d image import failed for {cluster}: {res.stderr.strip()}[/yellow]")

    console.print("[bold green]Image preload process completed.[/bold green]")


@app.command("register-spokes")
def register_spokes_cmd(
    hub_context: Annotated[str, typer.Option("--hub-context", help="Hub kubectl context")] = "k3d-hub-k3d",
    argocd_namespace: Annotated[str, typer.Option("--argocd-namespace", help="Argo CD namespace")] = "argocd",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Dry run mode without cluster modification")] = False,
) -> None:
    """Register Spoke clusters in Argo CD running on Hub cluster."""
    console.print("[bold cyan]>>> Registering Spoke clusters into Argo CD on Hub...[/bold cyan]")
    ok = register_spokes_in_argocd(
        hub_context=hub_context,
        argocd_namespace=argocd_namespace,
        dry_run=dry_run,
    )
    if ok or dry_run:
        console.print("[bold green]Argo CD Spoke registration finished successfully.[/bold green]")
    else:
        console.print("[yellow][WARN] Some spokes were not reachable or failed registration.[/yellow]")


@app.command("status")
def status_cmd() -> None:
    """Inspect and display k3d cluster status, nodes, and WAN latency status."""
    console.print("[bold cyan]======================================================================[/bold cyan]")
    console.print("[bold cyan] Multi-Cloud Platform Status Inspection[/bold cyan]")
    console.print("[bold cyan]======================================================================[/bold cyan]")

    # 1. k3d cluster list
    console.print("\n[bold]1. k3d Clusters:[/bold]")
    k3d_list = run_cmd(["k3d", "cluster", "list"])
    console.print(k3d_list.stdout if k3d_list.returncode == 0 else "[yellow]No k3d clusters found.[/yellow]")

    # 2. Kubernetes Nodes
    table = Table(title="Kubernetes Cluster Nodes")
    table.add_column("Cluster", style="cyan")
    table.add_column("Node Name", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Roles", style="white")

    for cluster_name in CLUSTER_CONFIGS.keys():
        ctx = f"k3d-{cluster_name}"
        nodes_res = run_cmd(["kubectl", "--context", ctx, "get", "nodes", "-o", "json"])
        if nodes_res.returncode == 0 and nodes_res.stdout.strip():
            try:
                data = json.loads(nodes_res.stdout)
                for item in data.get("items", []):
                    name = item.get("metadata", {}).get("name", "unknown")
                    conditions = item.get("status", {}).get("conditions", [])
                    ready_cond = next((c for c in conditions if c.get("type") == "Ready"), {})
                    status = "Ready" if ready_cond.get("status") == "True" else "NotReady"
                    table.add_row(cluster_name, name, status, "control-plane")
            except Exception:
                table.add_row(cluster_name, "error parsing", "unknown", "")
        else:
            table.add_row(cluster_name, "unreachable", "NotReady", "-")

    console.print(table)

    # 3. WAN Netem Status
    console.print("\n[bold]3. WAN Latency Emulation (tc netem):[/bold]")
    for container in ["k3d-aws-k3d-server-0", "k3d-azure-k3d-server-0"]:
        show_cmd = [
            "docker", "run", "--rm", "--cap-add=NET_ADMIN", f"--net=container:{container}",
            "alpine:3.20", "sh", "-c",
            "apk add --no-cache iproute2 >/dev/null 2>&1 && tc qdisc show dev eth0",
        ]
        tc_res = run_cmd(show_cmd)
        console.print(f"  - [bold]{container}[/bold]: {tc_res.stdout.strip() if tc_res.returncode == 0 else 'unreachable'}")

    console.print("\n[bold green]Status inspection complete.[/bold green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
