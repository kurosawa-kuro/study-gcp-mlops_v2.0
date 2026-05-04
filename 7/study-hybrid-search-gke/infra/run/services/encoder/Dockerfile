# KServe InferenceService: multilingual-e5-base encoder。
# Build context: repository root。Entry point: ml.serving.encoder。
# Phase 7 で base から ml extras を分離したので、'.[ml]' で sentence-transformers を要求する。

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AIP_HTTP_PORT=8080

WORKDIR /workspace

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml uv.lock* /workspace/
COPY ml /workspace/ml

RUN pip install --no-cache-dir '/workspace[ml]'

EXPOSE 8080
CMD ["python", "-m", "ml.serving.encoder"]
