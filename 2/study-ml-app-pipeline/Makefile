.DEFAULT_GOAL := help

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MONITOR_LOG_DIR ?= logs/run-all-monitor

PHASE_NAME := phase-2-app-pipeline
NA_TARGETS := up wait-db doctor sync logs api-refresh \
	lint fmt fmt-check typecheck check check-layers \
	db-migrate-% db-seed-% ops-bootstrap \
	tf-% deploy-all deploy-all-direct deploy-api deploy-api-local deploy-training-job-local deploy-kserve-models destroy-all \
	setup-% ops-monitor ops-monitor-lro ops-monitor-deploy \
	seed-test seed-test-clean train-smoke train-smoke-persist api-dev api-dev-search-rerank \
	ops-api-url ops-skew-% ops-search-volume ops-runs-recent ops-bq-scan-top ops-train-now ops-pipeline-run ops-reload-api ops-enable-search ops-promote-reranker ops-check-retrain ops-slo-status \
	ops-livez ops-search ops-search-components ops-ranking ops-feedback ops-label-seed ops-accuracy-report ops-daily ops-weekly \
	ops-sync ops-embed ops-train-build ops-train-fit ops-ranking-verbose eval-compare eval-offline kpi-daily eval-weekly-report features-daily features-report \
	bqml-train-popularity enrich-properties destroy-phase6-learning kube-creds local-accuracy-report

include ../../mk/base.mk

.PHONY: help build seed train serve test test-e2e install-browsers run-all-core run-all ops-run-all-monitor down clean free-ports

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

build: ## Build Docker images (docker compose build)
	docker compose build

seed: ## Seed sklearn California Housing into PostgreSQL
	$(PYTHON) scripts/local/setup/seed.py

train: ## Run LightGBM training
	$(PYTHON) scripts/local/setup/train.py

serve: ## Start FastAPI on :8000
	$(PYTHON) scripts/local/deploy/serve.py

test: ## Run pytest (local, E2E は除外)
	$(PYTHON) scripts/local/ops/test.py -m "not e2e"

test-e2e: ## Run Playwright E2E tests (要 install-browsers)
	$(PYTHON) scripts/local/ops/test.py -m e2e

install-browsers: ## Playwright 用の Chromium などブラウザをインストール
	$(PYTHON) -m playwright install chromium

run-all-core: ## Core flow (build → seed → train → test)
	$(MAKE) build
	$(MAKE) seed
	$(MAKE) train
	$(MAKE) test

ops-run-all-monitor: ## Monitor run-all progress and save logs
	@mkdir -p "$(MONITOR_LOG_DIR)"
	@log_file="$(MONITOR_LOG_DIR)/$$(date -u +%Y%m%dT%H%M%SZ)-run-all.log"; \
	echo "monitor-log: $$log_file"; \
	$(PYTHON) scripts/local/run_all_monitor.py --log-file "$$log_file" -- $(MAKE) run-all-core

run-all: ## End-to-end local flow via monitor (build → seed → train → test)
	$(MAKE) ops-run-all-monitor

verify-all: ## Alias of run-all-core for cross-phase teaching vocabulary
	$(MAKE) run-all-core

down: ## Stop and remove docker compose services
	docker compose down --remove-orphans

clean: ## docker compose down + remove generated files
	$(PYTHON) scripts/local/ops/clean.py

free-ports: ## Stop non-project containers binding host :5432/:8000
	$(PYTHON) -c "import sys; sys.path.insert(0, 'scripts'); from core import free_host_ports; free_host_ports()"
