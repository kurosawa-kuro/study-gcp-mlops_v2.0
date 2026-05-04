FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    lightgbm \
    pandas \
    numpy \
    scikit-learn \
    "pydantic-settings[yaml]" \
    "psycopg[binary]" \
    sqlalchemy

COPY app/ app/
COPY common/ common/
COPY ml/ ml/
COPY pipeline/ pipeline/
COPY env/config/ env/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "pipeline.training_job.main"]
