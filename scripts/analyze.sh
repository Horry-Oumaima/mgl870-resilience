#!/usr/bin/env bash
# Lance l'analyse dans un conteneur Python (aucune installation sur la machine).
# Usage : ./scripts/analyze.sh [campagne ...]   (par défaut : campagne_r100 campagne_r200)
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work -w /work \
  -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e PYTHONPATH=/tmp/deps \
  python:3.12-slim sh -c "pip install --quiet --disable-pip-version-check --no-cache-dir \
    --target /tmp/deps -r analysis/requirements.txt && python scripts/analyze.py $*"
