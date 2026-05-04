# syntax=docker/dockerfile:1.7
# GKE Deployment: search-api (FastAPI、KServe encoder/reranker への HTTP 委譲)。
# Build context: repository root。
#
# 重要: Phase 7 では encoder/reranker は KServe 側で動かすので、search-api image は
# `[ml]` extra (lightgbm + sentence-transformers + torch transitive) と
# `[pipelines]` extra (kfp + google-cloud-pipeline-components) を install しない。
# 結果: venv が ~5.4GB → ~457MB に縮む。pyproject.toml の optional-dependencies 参照。
#
# BuildKit `--mount=type=cache` で uv の wheel cache をビルド間で共有する。
# 初回 build: ~12 分 (3GB → 500MB に縮んでも upload bandwidth bound)。
# 2 回目以降の app 変更だけの build: cache hit で ~1 分前後を目標。

FROM ghcr.io/astral-sh/uv:0.5.4-python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Builder は依存解決のみ (third-party packages の wheel install)。
# プロジェクト本体は --no-install-project で venv に焼き込まない →
# venv は pyproject.toml / uv.lock が変わらない限り内容不変 = COPY layer cacheable。
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.12-slim-bookworm AS runtime

# useradd は COPY より上に置く。app 変更だけの build でキャッシュヒットする。
RUN useradd --system --uid 1001 --home-dir /home/app app \
    && mkdir -p /home/app

# venv (third-party only) を COPY する layer。pyproject.toml/uv.lock が変わらない限り cache hit。
COPY --from=builder --chown=app:app /opt/venv /opt/venv

# プロジェクト source は venv の外に置き、PYTHONPATH で読ませる (= editable install 相当)。
# app/ が変わっても venv layer (~500MB) は再 COPY されないので 2 回目以降の build が
# 数秒で終わる。pyproject.toml は wheel build を走らせず参照のみ。
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/home/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    LOG_AS_JSON=1 \
    GCP_LOGGING_ENABLED=1

COPY --chown=app:app ml /home/app/ml
COPY --chown=app:app scripts /home/app/scripts
# app/ は最も頻繁に変わるので最後に COPY する。
COPY --chown=app:app app /home/app/app

USER app
WORKDIR /home/app

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
