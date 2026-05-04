FROM python:3.12-slim

WORKDIR /app

# libgomp1 = LightGBM の OpenMP runtime。curl = healthcheck で使用。
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# uv をインストール。Phase 3-7 共通で uv を使う (pip / poetry 不可)。
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./

# 依存だけ先に解決してキャッシュ性を上げる。
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# multilingual-e5 small を image に焼き込む (初回起動の数分待ちを回避)。
ARG E5_MODEL_NAME=intfloat/multilingual-e5-small
ENV E5_MODEL_NAME=${E5_MODEL_NAME}
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${E5_MODEL_NAME}')"

COPY app/ app/
COPY ml/ ml/
COPY env/config/ env/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
