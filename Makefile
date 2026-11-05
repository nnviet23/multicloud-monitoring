# ==============================================================================
# Multi-Cloud Monitoring Platform - Master Automation Makefile
# ==============================================================================
# Prerequisites: Linux / WSL2 / macOS with docker, k3d, kubectl, helm, ansible
# ==============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

HUB_CTX    := k3d-hub-k3d
AWS_CTX    := k3d-aws-k3d
AZURE_CTX  := k3d-azure-k3d

.PHONY: help
help: ## Display this help message
	@echo "======================================================================"
	@echo " Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)"
	@echo "======================================================================"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "======================================================================"

.PHONY: env-setup
env-setup: ## Ensure .env file exists from template
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
	fi
	@cp .env k8s/overlays/local-k3d/hub/.env
	@cp .env.example k8s/overlays/local-k3d/hub/.env.example
	@echo ".env configuration is ready."

.PHONY: pull-images
pull-images: ## Pre-pull all version-pinned container images on host
	@bash infra/scripts/pull_images.sh

.PHONY: import-images
import-images: ## Import pre-pulled images into all 3 k3d clusters
	@bash infra/scripts/import_k3d_images.sh

.PHONY: pki-generate
pki-generate: ## Generate Root CA and mTLS 1.3 certificates for Hub & Spokes
	@echo "--> Generating PKI mTLS Certificates..."
	@bash security/pki/scripts/01-generate-ca.sh
	@bash security/pki/scripts/02-generate-hub-cert.sh
	@bash security/pki/scripts/03-generate-spoke-cert.sh
	@echo "PKI certificates generated successfully."

.PHONY: setup
setup: env-setup pull-images ## Run complete prerequisites setup (env + pull images)

.PHONY: infra
infra: pki-generate ## Provision 3 k3d clusters, WAN bridge, CoreDNS & mTLS secrets via Ansible
	@echo "--> Provisioning infrastructure via Ansible master playbook..."
	ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/site.yml
	@echo "Importing container images into freshly provisioned clusters..."
	@$(MAKE) import-images

.PHONY: deploy-hub
deploy-hub: ## Deploy complete Hub Observability Stack via Kustomize Overlay
	@echo "--> Deploying Hub Observability Stack on $(HUB_CTX)..."
	kubectl --context $(HUB_CTX) apply -k k8s/overlays/local-k3d/hub

.PHONY: deploy-spokes
deploy-spokes: ## Deploy TeaStore Workloads and Edge OTel Collectors on Spokes
	@echo "--> Deploying Compute Spoke on $(AWS_CTX)..."
	kubectl --context $(AWS_CTX) apply -k k8s/overlays/local-k3d/spoke-aws
	@echo "--> Deploying Data Spoke on $(AZURE_CTX)..."
	kubectl --context $(AZURE_CTX) apply -k k8s/overlays/local-k3d/spoke-azure

.PHONY: deploy
deploy: deploy-hub deploy-spokes ## Deploy complete system (Hub + Spoke 1 AWS + Spoke 2 Azure)
	@echo "======================================================================"
	@echo "Multi-Cloud System successfully deployed on all 3 clusters!"
	@echo "  - TeaStore WebUI:   http://localhost:8080/tools.descartes.teastore.webui/"
	@echo "  - Grafana:          http://localhost:3000 (admin / MultiCloudSecurePassword2026!)"
	@echo "  - MinIO Console:    http://localhost:9001 (admin / MultiCloudSecurePassword2026!)"
	@echo "  - Thanos Query UI:  http://localhost:9090"
	@echo "  - Pyrra SLO UI:     http://localhost:9099"
	@echo "======================================================================"

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

.PHONY: teardown
teardown: ## Clean up all k3d clusters, docker networks, volumes and certs
	@echo "--> Tearing down all clusters and resources..."
	ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/00_cleanup_all.yml

.PHONY: reset-wan
reset-wan: ## Reset simulated WAN impairment back to standard latency
	@echo "--> Resetting WAN netem configuration..."
	ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/99_reset_wan_emulation.yml

