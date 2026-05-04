# Shared Makefile skeleton for phase command vocabulary normalization.
#
# Usage (per phase Makefile):
#   PHASE_NAME := phase-3-local
#   NA_TARGETS := deploy-all tf-init ...
#   include ../../mk/base.mk
#
# Policy:
# - Keep command names globally consistent across phases.
# - Phase-specific inapplicable commands are overridden via NA_TARGETS.
# - run-all / verify-all are mandatory per-phase overrides.

BASE_MK_LOADED := 1

PHASE_NAME ?= unknown-phase
NA_MODE ?= success
NA_TARGETS ?=

.PHONY: help-all print-canonical-targets print-na-targets ops-monitor-run-all ops-monitor-deploy

# Canonical command vocabulary (max set). Keep names stable.
BASE_CANONICAL_TARGETS := \
	help doctor \
	up down clean free-ports wait-db \
	build sync \
	lint fmt fmt-check typecheck test test-e2e check check-layers install-browsers \
	db-migrate-core db-migrate-ops db-migrate-features db-migrate-embeddings db-migrate-learning db-migrate-eval db-seed-properties ops-bootstrap \
	seed seed-test seed-test-clean train-smoke train-smoke-persist \
	api-dev api-dev-search-rerank serve \
	tf-bootstrap tf-init tf-validate tf-fmt tf-fmt-fix tf-plan \
	deploy-all deploy-all-direct deploy-api deploy-api-local deploy-training-job-local deploy-kserve-models destroy-all \
	setup-encoder-endpoint setup-reranker-endpoint setup-model-monitoring setup-pipeline-schedule \
	ops-monitor ops-monitor-lro ops-monitor-deploy ops-monitor-run-all \
	ops-livez ops-search ops-search-components ops-ranking ops-ranking-verbose ops-feedback ops-label-seed ops-accuracy-report ops-daily ops-weekly \
	ops-sync ops-embed ops-train-build ops-train-fit ops-train-now ops-pipeline-run ops-reload-api ops-enable-search ops-promote-reranker ops-check-retrain \
	eval-compare eval-offline kpi-daily eval-weekly-report features-daily features-report \
	ops-api-url ops-skew-latest ops-skew-run ops-search-volume ops-runs-recent ops-bq-scan-top ops-slo-status \
	bqml-train-popularity enrich-properties destroy-phase6-learning \
	kube-creds \
	run-all run-all-core verify-all

help-all:
	@echo "Standard command vocabulary ($(PHASE_NAME))"
	@echo "----------------------------------------"
	@for t in $(BASE_CANONICAL_TARGETS); do \
		printf "  %s\n" "$$t"; \
	done
	@echo ""
	@if [ -n "$(NA_TARGETS)" ]; then \
		echo "N/A targets ($(PHASE_NAME)):"; \
		for t in $(NA_TARGETS); do printf "  %s\n" "$$t"; done; \
	fi

print-canonical-targets:
	@for t in $(BASE_CANONICAL_TARGETS); do \
		echo "$$t"; \
	done

print-na-targets:
	@for t in $(NA_TARGETS); do \
		echo "$$t"; \
	done

# Standardized monitor aliases.
ops-monitor-run-all:
	@$(MAKE) ops-run-all-monitor

ops-monitor-deploy:
	@$(MAKE) ops-deploy-monitor

# NA target generator.
define _DECLARE_NA_TARGET
$(1):
	@echo "[N/A][$(PHASE_NAME)] '$$(notdir $$@)' is not applicable in this phase"
	@if [ "$(NA_MODE)" = "error" ]; then exit 1; else exit 0; fi
endef

$(foreach t,$(NA_TARGETS),$(eval $(call _DECLARE_NA_TARGET,$(t))))
