#!/usr/bin/env bash
#
# Run the CIS Benchmark Web UI natively (no Docker).
# Creates a local virtualenv, installs deps, and starts the server.
#
#   ./run-local.sh
#   then open http://localhost:8000
#
# State (session + catalog.db) is kept in ./data, exports in ./work,
# mirroring the container layout so you can switch between them freely.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "${ROOT_DIR}"

PORT="${PORT:-8000}"
VENV="${VENV:-.venv}"

# Require Python 3.12+ (cis-bench needs it).
PYTHON="${PYTHON:-python3}"
if ! "${PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,12) else 1)'; then
  echo "ERROR: Python 3.12+ is required (found: $(${PYTHON} --version 2>&1))." >&2
  echo "Install Python 3.12+ or set PYTHON=/path/to/python3.12" >&2
  exit 1
fi

if [ ! -d "${VENV}" ]; then
  echo ">> Creating virtualenv in ${VENV}"
  "${PYTHON}" -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo ">> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Keep cis-bench state + exports inside the repo (parity with the container).
mkdir -p "${ROOT_DIR}/data/.cis-bench" "${ROOT_DIR}/work"
export HOME="${ROOT_DIR}/data"
export CIS_WORK_DIR="${ROOT_DIR}/work"
export CIS_BENCH_ENV="${CIS_BENCH_ENV:-production}"

echo ">> Starting Web UI on http://localhost:${PORT}  (Ctrl+C to stop)"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
