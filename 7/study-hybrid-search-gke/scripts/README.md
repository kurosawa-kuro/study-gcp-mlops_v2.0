# `scripts/` layout (Phase 7)

**Rule**: CLI entrypoints stay thin; reusable logic lives under topical packages.

| Area | Role |
|------|------|
| **`infra/`** | Terraform/GCP/kubectl helpers shared by deploy & destroy. Includes **`terraform_lock.py`** (remote state lock + opt-in unlock), **`terraform_stage_apply.py`** (`deploy-all` stage1 targets + 409 retries + lock handling). |
| **`setup/`** | One-shot orchestrators: **`deploy_all.py`**, **`destroy_all.py`** — ordering and step glue only; no duplicated Terraform loops. |
| **`deploy/`**, **`ci/`**, **`ops/`**, **`lib/`** | As existing docstrings describe. |

Adding new Terraform retry or lock behavior → extend **`infra/terraform_*.py`**, not the orchestrators.
