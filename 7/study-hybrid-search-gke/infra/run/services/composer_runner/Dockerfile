# syntax=docker/dockerfile:1.7
# Composer DAG runner image — Phase 7 V5 fix (2026-05-03)。
#
# **背景**: 過去 session の Claude が DAG を `BashOperator: uv run python -m scripts.X`
# で書いたが、Composer worker は uv 不在 / repo source 不在のため `task SUCCEEDED`
# 未達 (= canonical 未達 = ゴール劣化)。本 image は KubernetesPodOperator から
# `python -m <module>` を呼ぶ runner として機能する。
#
# 含むもの:
# - Python 3.12 + `[pipelines]` extra (kfp + google-cloud-pipeline-components)
#   * scripts.ops.check_retrain / promote / slo_status / vertex.pipeline_wait
#   * scripts.infra.feature_view_sync
#   * scripts.setup.backfill_vector_search_index (lazy import の vector search SDK)
#   * pipeline.workflow.compile (KFP 2.x、submit_train_pipeline 用)
# - gcloud SDK (apt 経由、~150MB)。`scripts.ops.promote` 等は Python SDK 経由
#   なので gcloud は使わないが、Dataform / Composer ops の便宜上同梱。
# - scripts/ + pipeline/ + ml/ source code (DAG が呼ぶ Python module)
#
# **意図的に含めないもの**: env/config/setting.yaml を image に含めない。
# Composer / Terraform が Pod に注入する env が **GCP 上の唯一の正本**であり、
# setting.yaml をビルドへ焼くと「yaml を都度いじればよい」という誤った運用を誘発する。
#
# 含まないもの:
# - app/ (FastAPI source、本 image は web server を立てない)
# - `[ml]` extra (torch + sentence-transformers ~2.5GB)。DAG task は ML 推論
#   や training を直接行わない (Vertex Pipelines に submit するだけ) ので不要。
#   含めると kaniko snapshot で OOM (exit 137)、build 失敗の原因になる
#   (2026-05-03 incident)。
#
# Image size 想定: ~700MB-1GB ([pipelines] の kfp ~200MB + python runtime +
# gcloud)。DAG task は 1 日数回しか起動しないので OK。
#
# Build: `gcloud builds submit --config infra/cloudbuild/cloudbuild-composer-runner.yaml .`
# または `make build-composer-runner`。

FROM ghcr.io/astral-sh/uv:0.5.4-python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# `[pipelines]` extra のみ install (kfp + google-cloud-pipeline-components)。
# `[ml]` (torch + sentence-transformers) は DAG が使わないので除外
# (snapshot OOM 回避、2026-05-03 incident)。
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra pipelines --no-install-project


FROM python:3.12-slim-bookworm AS runtime

# gcloud SDK を入れる (Dataform / Composer 系 CLI 操作用)。
# `apt-get install -y google-cloud-cli` は debian-slim では default repo に
# 無いため公式 apt リポジトリを追加する。
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        google-cloud-cli \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 1001 --home-dir /home/app app \
    && mkdir -p /home/app

COPY --from=builder --chown=app:app /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/home/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_AS_JSON=1 \
    GCP_LOGGING_ENABLED=1

# Composer worker の env_variables (REGION / VERTEX_LOCATION / GCP_PROJECT etc.)
# は KubernetesPodOperator が pod に注入する。本 image は env を hardcode しない。

COPY --chown=app:app ml /home/app/ml
COPY --chown=app:app scripts /home/app/scripts
COPY --chown=app:app pipeline /home/app/pipeline

USER app
WORKDIR /home/app

# entrypoint は KubernetesPodOperator 側で `cmds=["python"], arguments=["-m", "X"]`
# のように指定する。default は python REPL。
CMD ["python"]
