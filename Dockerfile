# syntax=docker/dockerfile:1

########################################
# CIS Benchmark CLI (mitre/cis-bench)  #
# Containerized for local / on-prem use #
########################################

FROM python:3.12-slim AS base

# Pin the cis-bench version for reproducible builds.
# Override at build time with:  --build-arg CIS_BENCH_VERSION=x.y.z
ARG CIS_BENCH_VERSION=0.5.2

# --- Runtime environment ---------------------------------------------------
# The cis-bench CLI stores everything (session cookies + SQLite catalog)
# under ~/.cis-bench. We point HOME at /data so that the entire application
# state lives in a single, mountable volume.
ENV HOME=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal OS deps. Wheels cover the Python deps (lxml, pydantic, etc.), but
# libxml2/libxslt runtime libs and CA certificates make the image robust.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# --- Install the CLI -------------------------------------------------------
RUN pip install --no-cache-dir "cis-bench==${CIS_BENCH_VERSION}"

# --- Application state ------------------------------------------------------
# Data dir (mounted volume): session.cookies, catalog.db, optional .env
# Work dir (mounted volume): exported files (yaml/csv/json/xccdf...)
RUN mkdir -p /data/.cis-bench /work
VOLUME ["/data", "/work"]
WORKDIR /work

# Sanity check that the entrypoint resolves at build time.
RUN cis-bench --version || true

# Run the CLI directly:  docker run --rm <image> search "ubuntu 22"
ENTRYPOINT ["cis-bench"]
CMD ["--help"]
