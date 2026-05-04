FROM python:3.12-slim

WORKDIR /app

# libgomp1 = LightGBM。
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./

RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# seed job も encoder model を使うので image に焼き込む。
ARG E5_MODEL_NAME=intfloat/multilingual-e5-small
ENV E5_MODEL_NAME=${E5_MODEL_NAME}
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${E5_MODEL_NAME}')"

COPY app/ app/
COPY ml/ ml/
COPY pipeline/ pipeline/
COPY env/config/ env/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# entrypoint は docker-compose.yml の `command:` で seed / trainer / evaluator を切り替える。
CMD ["python", "-m", "pipeline.data_job.main"]
