# syntax=docker/dockerfile:1

##############################################################
# CIS Benchmark — CLI + Web UI (wraps mitre/cis-bench)       #
# One image, two entrypoints:                                #
#   - Web UI : uvicorn app.main:app   (default CMD)          #
#   - CLI    : cis-bench <args>       (override entrypoint)  #
##############################################################

FROM python:3.12-slim AS base

ARG CIS_BENCH_VERSION=0.5.2

# The cis-bench CLI keeps its state under ~/.cis-bench. Pointing HOME at
# /data puts session cookies + catalog.db in a single mountable volume.
ENV HOME=/data \
    CIS_WORK_DIR=/work \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install Python deps first (better layer caching). requirements.txt pins
# cis-bench alongside FastAPI/uvicorn for the web UI.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "cis-bench==${CIS_BENCH_VERSION}"

# App code.
COPY app ./app

# State + work directories. (No Docker VOLUME instruction: Railway rejects it
# and manages persistence via its own Volumes; local compose bind-mounts these.
# Attach a Railway Volume at /data to persist the session + catalog.db.)
RUN mkdir -p /data/.cis-bench /work

RUN cis-bench --version || true

EXPOSE 8000

# Default: start the web UI. Binds to $PORT when set (Railway/Render/Fly set it),
# otherwise 8000. Shell form so the variable is expanded at runtime.
# Override the entrypoint for CLI-only use (see the `cli` service in compose).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
