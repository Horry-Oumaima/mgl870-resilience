#!/usr/bin/env bash
# Lance une charge k6. Usage : ./scripts/load.sh <nom_du_dossier> [RATE] [DURATION]
set -euo pipefail
OUT="${1:?Indique un nom de dossier, par exemple test1}"
RATE="${2:-100}"
DURATION="${3:-180s}"
mkdir -p "results/$OUT"
docker compose run --rm \
  -e RATE="$RATE" -e DURATION="$DURATION" -e OUT_DIR="/results/$OUT" \
  k6 run --quiet --console-output "/results/$OUT/requests.log" /scripts/load.js
