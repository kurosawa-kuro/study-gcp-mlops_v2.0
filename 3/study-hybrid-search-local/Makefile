SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,uv run python)
COMPOSE := docker compose

PHASE_NAME := phase-3-local
# Phase 3 ではクラウド系 / KServe / Composer / Vertex / BQML 系は N/A。
NA_TARGETS := \
	tf-bootstrap tf-init tf-validate tf-fmt tf-fmt-fix tf-plan \
	deploy-all deploy-all-direct deploy-api deploy-api-local deploy-training-job-local deploy-kserve-models destroy-all \
	setup-encoder-endpoint setup-reranker-endpoint setup-model-monitoring setup-pipeline-schedule \
	ops-monitor ops-monitor-lro ops-monitor-deploy \
	ops-livez ops-search ops-search-components ops-ranking ops-ranking-verbose \
	ops-feedback ops-label-seed ops-accuracy-report ops-daily ops-weekly \
	ops-sync ops-embed ops-train-build ops-train-fit ops-train-now ops-pipeline-run \
	ops-reload-api ops-enable-search ops-promote-reranker ops-check-retrain \
	ops-api-url ops-skew-latest ops-skew-run ops-search-volume ops-runs-recent \
	ops-bq-scan-top ops-slo-status \
	bqml-train-popularity enrich-properties destroy-phase6-learning kube-creds \
	eval-compare eval-offline kpi-daily eval-weekly-report features-daily features-report \
	api-dev-search-rerank ops-bootstrap

include ../../mk/base.mk

.PHONY: help doctor sync build seed train evaluate serve api-dev test check check-layers \
	verify-pipeline run-all-core run-all verify-all down clean wait-db

help: ## Show this help
	@echo "Phase 3 (Local hybrid search) — quick start: make build && make seed && make train && make serve"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

doctor: ## Verify prerequisite tools (uv / docker / make)
	@command -v uv >/dev/null 2>&1 && echo "  ✓ uv" || (echo "  ✗ uv not found"; exit 1)
	@command -v docker >/dev/null 2>&1 && echo "  ✓ docker" || (echo "  ✗ docker not found"; exit 1)
	@$(COMPOSE) version >/dev/null 2>&1 && echo "  ✓ docker compose" || (echo "  ✗ docker compose not found"; exit 1)

sync: ## uv workspace + dev group 同期
	uv sync --all-extras --dev

build: ## Build Docker images (postgres+pgvector / meilisearch / redis / search-api)
	$(COMPOSE) build

up: ## docker compose up -d (postgres / meilisearch / redis のみ起動)
	$(COMPOSE) up -d postgres meilisearch redis
	@$(MAKE) wait-db

wait-db: ## postgres healthcheck PASS まで待つ
	@printf "Waiting postgres "
	@for i in $$(seq 1 30); do \
		if $(COMPOSE) exec -T postgres pg_isready -U admin -d hybrid_search >/dev/null 2>&1; then \
			echo " OK"; exit 0; \
		fi; \
		printf "."; sleep 1; \
	done; \
	echo " timeout"; exit 1

seed: ## synthetic 不動産データ → PostgreSQL + Meilisearch + pgvector
	$(COMPOSE) run --rm seed

train: ## LightGBM LambdaRank 学習 → ml/registry/artifacts/{run_id}/model.lgb
	$(COMPOSE) run --rm trainer

evaluate: ## NDCG@10 / MAP / Recall@20 の hold-out 評価 → metrics.json
	$(COMPOSE) run --rm evaluator

serve: ## search-api を :8000 で起動 (foreground)
	$(COMPOSE) up search-api

api-dev: ## ローカル uvicorn (Docker なし、uv run。前提: postgres/meili/redis は up 済)
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test: ## pytest 全体 (ローカル)
	uv run pytest tests/unit -q

check: ## ローカル CI 同等 (ruff + ruff format --check + mypy + pytest)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app ml pipeline
	uv run pytest tests/unit -q

check-layers: ## Port-Adapter 境界の AST 検査
	uv run python -m scripts.ci.layers

verify-pipeline: ## seed → train → serve の integration E2E (docker compose 立ち上げ済前提)
	uv run pytest tests/integration -q

run-all-core: ## build → seed → train → test を 1 コマンドで
	$(MAKE) build
	$(MAKE) up
	$(MAKE) seed
	$(MAKE) train
	$(MAKE) test

run-all: ## run-all-core の alias
	$(MAKE) run-all-core

verify-all: ## verify-pipeline の alias (Phase 横断 vocabulary)
	$(MAKE) verify-pipeline

down: ## docker compose down (volume 残す)
	$(COMPOSE) down --remove-orphans

clean: ## down + 生成物削除 (model artifacts / volumes)
	$(COMPOSE) down --remove-orphans --volumes
	rm -rf ml/registry/artifacts/*
