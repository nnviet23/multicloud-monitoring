# Multicloud Monitoring

> A secure, lightweight, and cost-aware multi-cloud observability framework with adaptive anomaly detection and root-cause analysis.

Multicloud Monitoring resolves cross-cloud telemetry fragmentation, high WAN egress costs, and telemetry eavesdropping across distributed Kubernetes environments. It standardizes Metrics, Logs, and Traces using edge-optimized OpenTelemetry Collectors with mutual TLS (mTLS), storing telemetry centrally in Thanos, Loki, Tempo, and MinIO. Built-in deep learning autoencoders and Likelihood-based scoring detect anomalies in real time without static threshold decay.

## Features

- Full Three-Pillar Observability: Unified collection of Metrics, Logs, and Traces using standardized OpenTelemetry Collectors.
- Egress & Overhead Reduction: Edge filtering, large-batch processing (512–1024 spans), and 3% probabilistic sampling maintain agent overhead below 5%.
- Zero-Trust Transport Security: Mutual TLS (mTLS) identity verification and TLS 1.3 encryption for OTLP streams across emulated WAN boundaries.
- Centralized High-Throughput Storage: Sub-5-second query latency powered by Hub-centralized Prometheus, Thanos, Loki, and Tempo with MinIO S3 object storage.
- Adaptive Likelihood Anomaly Detection: Dual-sliding-window scoring on GRU, TCN, and Isolation Forest reconstruction errors to mitigate geometric shift and alert fatigue.
- TeaStore Microservices Benchmark: Validated against realistic multi-tier shopping workflows partitioned across emulated cloud clusters.

## Benchmark Application

This system uses the open-source **[TeaStore](https://github.com/DescartesResearch/TeaStore)** microservices testbed as its primary validation workload:
- Compute services (`WebUI`, `Auth`, `ImageProvider`, `Recommender`) run on Spoke 1 (`aws-k3d`).
- Data persistence services (`Persistence`, `MySQL`) execute on Spoke 2 (`azure-k3d`).
- Cross-cluster traffic is routed through emulated WAN bridges (`tc/netem`) with a 10 ms RTT delay and 0.1% packet loss.

## Getting Started

### Prerequisites

- Ubuntu 24.04+ (amd64 / arm64)
- Docker Engine 24.0+
- Ansible 2.14+
- `k3d`, `kubectl`, and `helm` CLI tools

### Installation

```bash
git clone https://github.com/nnviet23/multicloud-monitoring.git
cd multicloud-monitoring
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host.yml --ask-become-pass
```
## Running Locally
### 1. Provision clusters and emulated WAN latency:

```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_create_clusters.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_setup_wan_emulation.yml
```
### 2. Generate mTLS certificates and deploy workloads:

```bash
bash security/certs/generate_certs.sh
make deploy-hub
make deploy-spokes
```

### 3. Launch the anomaly detection engine:

```bash
cd ai-engine && python inference/detector.py
```
Access Grafana at http://localhost:3000 (credentials: admin / admin).

## Configuration

| Variable | Description | Default |
| --- | --- | --- |
| `WAN_INTERFACE` | Bridge interface for network emulation | `multi-cloud-wan` |
| `WAN_DELAY` | Simulated inter-cloud round-trip latency | 10ms |
| `WAN_LOSS` | Simulated inter-cloud packet drop rate | 0.1%  |
| `OTEL_BATCH_SIZE` | Telemetry batch size for Spoke collectors | 512 |
| `TRACE_SAMPLE_RATE` | Head-based trace sampling percentage | 0.03 |
| `MINIO_ROOT_USER` | Admin username for MinIO storage | admin |
| `ANOMALY_WINDOW_LONG` | Background reference sliding window size | 120 |
| `ANOMALY_WINDOW_SHORT` | Instantaneous sliding window size | 10 |

## Contributing
| Full Name | ID | Responsibility |
| --- | --- | --- |
| `Huỳnh Hữu Dũng` | 23127352 | `PKI, mTLS for OTLP` |
| `Đinh Tuấn Duy` | 23127356 | `Developing time-series models (GRU, TCN, Isolation Forest), a likelihood scoring algorithm, a RAG-based pipeline for root cause analysis (RCA), and chaos engineering fault-injection scenarios.` |
| `Nguyễn Nam Việt` | 23127517 | `Infrastructure automation (Ansible, Docker, k3d), virtual WAN configuration (tc/netem), deployment of the storage layer (MinIO, Thanos, Loki, Tempo, Grafana), and integration of TeaStore.` |

## License
Distributed under the MIT License. See `LICENSE` for more information.