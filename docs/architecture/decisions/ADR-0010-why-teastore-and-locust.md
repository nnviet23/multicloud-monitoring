# ADR-0010: Why SPEC RG TeaStore and Locust for Benchmarking

## Status
Accepted

## Context
To quantitatively evaluate the multi-cloud observability platform, SLO alerting, and AIOps root-cause analysis (RCA), we need a realistic, peer-reviewed microservice benchmark application that supports natural compute/data partitioning across `aws-k3d` and `azure-k3d`, paired with a repeatable, code-defined workload generator that runs headless in CI/CD.

## Decision
We adopt **SPEC RG TeaStore** as the official benchmark application and **Locust** (`locustfile.py`) as the official workload generator:
- **Multi-cluster partitioning:** Compute services (`teastore-webui`, `teastore-auth`, `teastore-recommender`, `teastore-image`, `teastore-registry`) run on `aws-k3d`; persistence (`teastore-persistence`, `teastore-db` MySQL 8.0) runs on `azure-k3d`.
- **Workload modeling:** `locustfile.py` simulates e-commerce user flows (60% browse, 25% cart, 15% checkout) across steady-state baselines (20–50 users) and spike tests (200–300 users), supplemented by `tests/chaos/run_service_faults.py` for automated fault-injection probes.
- **End-to-end tracing:** OTel Javaagent propagates W3C `traceparent` headers across clusters from `teastore-webui` to `teastore-db`.

## Alternatives Considered
- **Google Online Boutique:** Lacks a rich relational database tier and SPEC RG academic benchmarking pedigree.
- **Spring PetClinic Microservices:** Limited e-commerce and recommendation workloads.
- **JMeter / k6:** JMeter is heavy on GUI/RAM; k6 uses JavaScript, whereas Python-based Locust integrates directly with the project's AIOps and telemetry verification scripts.

## Consequences
- **Positive:** Academically recognized benchmark; reproducible Python-defined workloads; clearly exposes cross-cluster WAN latency between compute and persistence tiers.
- **Trade-offs:** Java/Tomcat containers require ~250–350 MB RAM each (requiring careful `-Xmx`/`-Xms` tuning) and initial MySQL database seeding on cluster creation.
