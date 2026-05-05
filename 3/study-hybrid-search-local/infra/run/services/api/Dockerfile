FROM python:3.12-slim

WORKDIR /app

# libgomp1 = LightGBM の OpenMP runtime。curl = healthcheck で使用。
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# uv をインストール。Phase 3-7 共通で uv を使う (pip / poetry 不可)。
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./

# 依存だけ先に解決してキャッシュ性を上げる (project 自体は app/ml/pipeline COPY 後に PYTHONPATH で読む)。
RUN uv sync --no-dev --no-install-project --frozen 2>/dev/null \
    || uv sync --no-dev --no-install-project

# multilingual-e5 model は **image に焼き込まない**。
# 理由: image size 削減 (470MB 削減) + build キャッシュ無効化を避ける。
# 初回起動時に sentence-transformers が download し、`hf_cache` volume で永続化される
# (docker-compose.yml の volumes 参照)。2 回目以降の起動は cache hit で数秒。
ARG E5_MODEL_NAME=intfloat/multilingual-e5-small
ENV E5_MODEL_NAME=${E5_MODEL_NAME}

COPY app/ app/
COPY ml/ ml/
COPY env/config/ env/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# uv が作る .venv を default Python に (uv run なしでも venv の Python が使われる)。
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
