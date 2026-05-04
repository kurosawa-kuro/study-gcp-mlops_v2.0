FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    lightgbm \
    numpy \
    pandas \
    fastapi \
    uvicorn \
    jinja2 \
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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
