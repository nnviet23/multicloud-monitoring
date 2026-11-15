.DEFAULT_GOAL := help
PYTHON ?= python3

.PHONY: help validate discovery generate experiment accuracy perf-smoke perf test

help:
	@echo "validate  Validate YAML configuration"
	@echo "discovery Print discovery artifacts"
	@echo "generate  Generate synthetic ground truth (dry-run)"
	@echo "experiment Run the small end-to-end experiment"
	@echo "accuracy  Reserved for run-specific accuracy processing"
	@echo "perf-smoke  Run a short performance measurement smoke test"
	@echo "perf        Run the full performance measurement"
	@echo "test      Run measurement tests"

validate:
	$(PYTHON) -m common.config --validate

discovery:
	@echo "See docs/architecture-discovery.md, docs/endpoint-inventory.md and docs/metric-mapping.md"

generate:
	$(PYTHON) -m workloads.generator --scenario small

experiment:
	$(PYTHON) -m workloads.run_experiment --scenario small --sources aws,azure

accuracy:
	@echo "Use 'make experiment' for a complete measured accuracy run."

perf-smoke:
	$(PYTHON) -m experiments.performance --config config/performance.yaml --mode smoke

perf:
	$(PYTHON) -m experiments.performance --config config/performance.yaml --mode full

test:
	$(PYTHON) -m pytest -q
