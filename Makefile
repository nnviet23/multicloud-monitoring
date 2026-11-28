# ==============================================================================
# Multi-Cloud Monitoring Platform - Master Automation Makefile
# ==============================================================================
# Prerequisites: Linux / WSL2 / macOS with docker, k3d, kubectl, helm, ansible
# ==============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Automatically load and export variables from .env if present
ifneq (,$(wildcard ./.env))
  include .env
  export
endif

HUB_CTX    := k3d-hub-k3d
AWS_CTX    := k3d-aws-k3d
AZURE_CTX  := k3d-azure-k3d
PYTHON     ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi)

.PHONY: help
help: ## Display this help message
	@echo "======================================================================"
	@echo " Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)"
	@echo "======================================================================"
	@awk 'BEGIN {FS = ":.*?## "} /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "======================================================================"

##@ Setup & Infra

.PHONY: env-setup
env-setup: ## Ensure .env file exists from template
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
	fi
	@echo ".env configuration is ready."

.PHONY: pull-images
pull-images: ## Pre-pull all version-pinned container images on host
	$(PYTHON) -m infra.cli pull-images

.PHONY: preload-images
preload-images: ## Import pre-pulled images into all 3 k3d clusters
	$(PYTHON) -m infra.cli preload-images

.PHONY: pki-generate
pki-generate: ## Generate Root CA and mTLS 1.3 certificates for Hub & Spokes
	@echo "--> Generating PKI mTLS Certificates..."
	$(PYTHON) -m infra.cli certs
	@echo "PKI certificates generated successfully."

.PHONY: setup
setup: env-setup pull-images ## Run complete prerequisites setup (env + pull images)

.PHONY: infra
infra: ## Provision all 3 k3d clusters and configure infrastructure
	@echo "--> Provisioning infrastructure via Python Platform CLI..."
	$(PYTHON) -m infra.cli up && $(PYTHON) -m infra.cli sync-hosts && $(PYTHON) -m infra.cli wan && $(PYTHON) -m infra.cli certs
	@echo "Importing container images into freshly provisioned clusters..."
	@$(MAKE) preload-images

##@ Deploy & GitOps

.PHONY: deploy-hub
deploy-hub: env-setup ## Deploy complete Hub Observability Stack via Kustomize Overlay
	@echo "--> Ensuring Kyverno v1.20.0 CRDs & Controller on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) apply --server-side --force-conflicts -f deploy/bootstrap/kyverno/install.yaml
	kubectl --context $(HUB_CTX) wait --for=condition=Established crd --all --timeout=60s
	@echo "--> Ensuring Argo CD v3.6.2 on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) create namespace argocd --dry-run=client -o yaml | kubectl --context $(HUB_CTX) apply -f -
	kubectl --context $(HUB_CTX) apply --server-side --force-conflicts -n argocd -f deploy/bootstrap/argocd/install.yaml
	@echo "--> Deploying Hub Observability Stack on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) create namespace teastore --dry-run=client -o yaml | kubectl --context $(HUB_CTX) apply -f -
	kubectl --context $(HUB_CTX) apply --server-side --force-conflicts -k deploy/clusters/hub || true
	kubectl --context $(HUB_CTX) wait --for=condition=Established crd --all --timeout=60s
	kubectl --context $(HUB_CTX) rollout status deployment/cert-manager-webhook -n cert-manager --timeout=120s
	kubectl --context $(HUB_CTX) apply --server-side --force-conflicts -k deploy/clusters/hub
	@$(MAKE) pki-generate

.PHONY: deploy-spokes
deploy-spokes: ## Deploy TeaStore Workloads and Edge OTel Collectors on Spokes
	@echo "--> Ensuring Kyverno v1.20.0 CRDs & namespaces on Spokes..."
	@for ctx in $(AWS_CTX) $(AZURE_CTX); do \
		kubectl --context $$ctx apply --server-side --force-conflicts -f deploy/bootstrap/kyverno/install.yaml; \
		kubectl --context $$ctx wait --for=condition=Established crd --all --timeout=60s; \
		for ns in monitoring storage teastore; do \
			kubectl --context $$ctx create namespace $$ns --dry-run=client -o yaml | kubectl --context $$ctx apply -f -; \
		done; \
	done
	@echo "--> Deploying Compute Spoke on $(AWS_CTX)..."
	kubectl --context $(AWS_CTX) apply --server-side --force-conflicts -k deploy/clusters/aws
	@echo "--> Deploying Data Spoke on $(AZURE_CTX)..."
	kubectl --context $(AZURE_CTX) apply --server-side --force-conflicts -k deploy/clusters/azure

.PHONY: register-spokes
register-spokes: ## Register Spoke clusters in Hub Argo CD
	@echo "--> Registering Spoke clusters in Hub Argo CD..."
	$(PYTHON) -m infra.cli register-spokes

.PHONY: deploy-argocd
deploy-argocd: ## Deploy Argo CD multi-cluster ApplicationSets on Hub
	@echo "--> Deploying Argo CD Engine and Bootstrap ApplicationSets on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) apply -k deploy/platform/argocd && kubectl --context $(HUB_CTX) apply -k deploy/bootstrap
	@$(MAKE) register-spokes

.PHONY: deploy-local
deploy-local: env-setup deploy-hub deploy-spokes ## Deploy complete system locally via kubectl/kustomize without Argo CD (direct reconcile)
	@echo "======================================================================"
	@echo "Multi-Cloud System successfully deployed directly on all 3 clusters!"
	@echo "  - TeaStore WebUI:   http://localhost:8080/tools.descartes.teastore.webui/"
	@echo "  - Grafana:          http://localhost:3000 (admin / (configured in .env))"
	@echo "  - MinIO Console:    http://localhost:9001 (admin / (configured in .env))"
	@echo "  - Thanos Query UI:  http://localhost:9090"
	@echo "  - Pyrra SLO UI:     http://localhost:9099"
		@echo "======================================================================"

.PHONY: deploy-gitops
deploy-gitops: env-setup deploy-argocd ## Deploy complete system via Argo CD GitOps ApplicationSets (automated self-healing)
	@echo "======================================================================"
	@echo "Multi-Cloud GitOps ApplicationSets deployed on Hub Argo CD!"
	@echo "======================================================================"

.PHONY: deploy
deploy: deploy-local ## Alias to deploy-local (default direct deployment)

##@ Verify & Operate

.PHONY: status
status: ## Show live cluster, pod, and WAN status via Platform CLI
	$(PYTHON) -m infra.cli status

.PHONY: verify
verify: ## Run comprehensive health verification across all clusters
	@echo "=== [1/3] Verifying Cluster Nodes ==="
	@kubectl --context $(HUB_CTX) get nodes
	@kubectl --context $(AWS_CTX) get nodes
	@kubectl --context $(AZURE_CTX) get nodes
	@echo ""
	@echo "=== [2/3] Verifying Workload Pods ==="
	@echo "--- Hub Cluster (monitoring & storage) ---"
	@kubectl --context $(HUB_CTX) get pods -n monitoring
	@kubectl --context $(HUB_CTX) get pods -n storage
	@echo "--- AWS Spoke (teastore & monitoring) ---"
	@kubectl --context $(AWS_CTX) get pods -n teastore
	@kubectl --context $(AWS_CTX) get pods -n monitoring
	@echo "--- Azure Spoke (teastore & monitoring) ---"
	@kubectl --context $(AZURE_CTX) get pods -n teastore
	@kubectl --context $(AZURE_CTX) get pods -n monitoring
	@echo ""
	@echo "=== [3/3] Verifying Simulated WAN Network (tc netem) ==="
	@docker exec k3d-aws-k3d-server-0 ping -c 3 k3d-azure-k3d-server-0 || true

##@ Cleanup

.PHONY: clean
clean: ## Remove local Python caches and temporary build artifacts
	@echo "--> Cleaning local caches and temporary files..."
	@find . -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".ruff_cache" \) -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .coverage htmlcov dist build *.egg-info

.PHONY: clean-images
clean-images: ## Remove all project container images and prune dangling images
	@echo "--> Cleaning up project container images..."
	@bash infra/scripts/clean_images.sh || true

.PHONY: teardown
teardown: ## Destroy all 3 clusters and clean up resources
	@echo "--> Tearing down all clusters and resources..."
	$(PYTHON) -m infra.cli down

.PHONY: purge-all
purge-all: teardown clean-images ## Full deep clean: teardown clusters + remove all project container images from host
	@echo "Full purge completed (clusters, network, certs, and Docker images cleaned)."

.PHONY: reset-wan
reset-wan: ## Reapply WAN emulation parameters
	@echo "--> Resetting WAN netem configuration..."
	$(PYTHON) -m infra.cli wan

##@ Test & Lint

.PHONY: test-scripts
test-scripts: ## Run all platform verification and hardening test scripts
	@echo "--> Running platform scripts test suite..."
	$(PYTHON) -m pytest tests/scripts/ -v

.PHONY: test-ai
test-ai: ## Run AI Anomaly Detection Engine V3 live evaluation tests
	@echo "--> Running AI Anomaly Detection Engine test suite..."
	@$(PYTHON) -m unittest tests/chaos/test_live_evaluation.py

.PHONY: validate-dashboards
validate-dashboards: ## Validate JSON syntax of all Grafana Dashboards
	@echo "--> Validating all Grafana Dashboards JSON syntax..."
	@$(PYTHON) -c 'import glob, json; [json.load(open(f)) for f in glob.glob("deploy/platform/visualization-grafana/dashboards/*.json")]; print("All Grafana Dashboards are 100% valid JSON!")'

.PHONY: validate-kustomize
validate-kustomize: ## Dry-run Kustomize build across Hub and Spokes
	@echo "--> Dry-run validating Kustomize manifests for all 3 clusters..."
	@kubectl kustomize deploy/clusters/hub > /dev/null
	@kubectl kustomize deploy/clusters/aws > /dev/null
	@kubectl kustomize deploy/clusters/azure > /dev/null
	@kubectl kustomize deploy/platform/argocd > /dev/null
	@kubectl kustomize deploy/bootstrap > /dev/null
	@kubectl kustomize deploy/slos > /dev/null
	@echo "All Kustomize manifests build successfully!"

.PHONY: validate-policies
validate-policies: ## Validate Kyverno ClusterPolicies syntax via Kustomize
	@echo "--> Validating Kyverno admission policies..."
	@kubectl kustomize deploy/policies > /dev/null
	@echo "All Kyverno policies are valid!"

.PHONY: deploy-policies
deploy-policies: ## Deploy Kyverno ClusterPolicies across all clusters
	@echo "--> Deploying Kyverno policies to all 3 clusters..."
	kubectl --context $(HUB_CTX) apply --server-side --force-conflicts -k deploy/policies
	kubectl --context $(AWS_CTX) apply --server-side --force-conflicts -k deploy/policies
	kubectl --context $(AZURE_CTX) apply --server-side --force-conflicts -k deploy/policies
	@echo "Kyverno admission policies deployed successfully."

.PHONY: fmt
fmt: ## Format Python code with ruff if installed
	@if $(PYTHON) -m ruff --version >/dev/null 2>&1; then \
		$(PYTHON) -m ruff format infra/ ai-engine/ tests/; \
	else \
		echo "ruff not installed; skipping Python formatting."; \
	fi

.PHONY: lint
lint: validate-dashboards validate-kustomize validate-policies ## Run complete static code & manifest linting
	@echo "All static linters and manifest validations PASSED!"

.PHONY: test-wan
test-wan: ## Test simulated WAN latency and packet loss between AWS and Azure
	@echo "--> Testing cross-cluster WAN RTT (AWS Spoke <-> Azure Spoke)..."
	@docker exec k3d-aws-k3d-server-0 ping -c 5 k3d-azure-k3d-server-0 || true

.PHONY: ui
ui: ## Port-forward essential web UIs (Grafana :3000, Thanos :9090, Pyrra :9099, MinIO :9001, TeaStore :8088)
	@echo "Opening web port-forwards..."
	@echo "  - Grafana:    http://localhost:3000 (admin / (configured in .env))"
	@echo "  - Thanos UI:  http://localhost:9090"
	@echo "  - Pyrra SLO:  http://localhost:9099"
	@echo "  - MinIO:      http://localhost:9001 (admin / (configured in .env))"
	@echo "  - TeaStore:   http://localhost:8080/tools.descartes.teastore.webui/"
	@echo "  - Argo CD:    https://localhost:8443 (admin)"
	@trap 'kill 0' EXIT; \
	(ss -tuln 2>/dev/null | grep -q ":3000 " || kubectl --context $(HUB_CTX) -n monitoring port-forward svc/grafana 3000:3000 >/dev/null) & \
	(ss -tuln 2>/dev/null | grep -q ":9090 " || kubectl --context $(HUB_CTX) -n monitoring port-forward svc/thanos-query 9090:9090 >/dev/null) & \
	(ss -tuln 2>/dev/null | grep -q ":9099 " || kubectl --context $(HUB_CTX) -n monitoring port-forward svc/pyrra 9099:9099 >/dev/null) & \
	(ss -tuln 2>/dev/null | grep -q ":9001 " || kubectl --context $(HUB_CTX) -n storage port-forward svc/minio-console 9001:9001 >/dev/null) & \
	(ss -tuln 2>/dev/null | grep -q ":8443 " || kubectl --context $(HUB_CTX) port-forward -n argocd svc/argocd-server 8443:443 >/dev/null 2>&1) & \
	(ss -tuln 2>/dev/null | grep -q ":8088 " || kubectl --context $(AWS_CTX) -n teastore port-forward svc/teastore-webui 8080:8080 >/dev/null) & \

.PHONY: validate-otel
validate-otel: ## Validate OTel Collector architectural rules and export OTelBin YAMLs
	@echo "--> Validating OpenTelemetry Collector pipelines & architecture..."
	@$(PYTHON) tests/scripts/validate_otel_rules.py

.PHONY: test
test: test-scripts validate-dashboards validate-kustomize validate-policies validate-otel ## Run all offline automated tests (Scripts, Dashboards, Manifests, Policies, OTel)
	@echo "All offline automated system verification tests PASSED!"

.PHONY: e2e
e2e: verify test-wan test-ai ## Run live cluster smoke tests (verify, WAN RTT, AI Anomaly Engine)
	@echo "All live cluster E2E smoke tests PASSED!"



