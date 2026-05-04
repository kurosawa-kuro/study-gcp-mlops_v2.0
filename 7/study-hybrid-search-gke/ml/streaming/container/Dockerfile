# Phase 6 T2 — Dataflow Flex Template container.
#
# Base image follows Google's Flex Template convention: gcr.io/dataflow-templates-base/python3-template-launcher-base.
# Builds a wheel containing ml.streaming.pipeline and invokes it via the
# template launcher. Kept minimal; the heavy apache-beam dep is resolved
# at launch time by the launcher.
FROM gcr.io/dataflow-templates-base/python3-template-launcher-base:latest

ARG WORKDIR=/dataflow/template
WORKDIR ${WORKDIR}

COPY ml/streaming/container/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ml/streaming ./ml/streaming

ENV FLEX_TEMPLATE_PYTHON_PY_FILE="${WORKDIR}/ml/streaming/pipeline.py"
ENV PYTHONPATH="${WORKDIR}"

# Sanity: the base image's entrypoint invokes FLEX_TEMPLATE_PYTHON_PY_FILE
# with the user-supplied parameters. Nothing else to do here.
