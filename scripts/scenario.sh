#!/usr/bin/env bash
# Applique un scénario de défaillance (S0 à S6) au laboratoire.
# Usage : ./scripts/scenario.sh <S0|S1|S2|S3|S4|S5a|S5b|S6|reset|status>
set -euo pipefail

TOXI="${TOXI_URL:-http://localhost:8474}"          # API de Toxiproxy
PAYMENT="${PAYMENT_URL:-http://localhost:8081}"    # Service B
PROXY="payment"
S6_START="${S6_START:-60}"          # S6 : secondes de fonctionnement normal avant la panne
S6_DURATION="${S6_DURATION:-30}"    # S6 : durée de la panne (secondes)
EVENTS="${EVENTS_FILE:-/dev/null}"  # fichier où noter l'heure des événements

log() { echo "$(date +%s.%N) $1" | tee -a "$EVENTS"; }

# Remet tout à la normale : aucun sabotage réseau, B sans erreur et à 50 ms
reset_all() {
  curl -sf -X POST "$TOXI/reset" > /dev/null
  curl -sf -X POST "$PAYMENT/admin/config?errorRate=0&baseDelayMs=50" > /dev/null
}

# Ajoute un sabotage Toxiproxy : nom, type, attributs JSON
toxic() {
  curl -sf -X POST "$TOXI/proxies/$PROXY/toxics" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$1\",\"type\":\"$2\",\"stream\":\"downstream\",\"attributes\":$3}" > /dev/null
}

# Règle le taux d'erreur de B
errors() {
  curl -sf -X POST "$PAYMENT/admin/config?errorRate=$1" > /dev/null
}

# Désactive le proxy : A obtient « connexion refusée », comme si B était arrêté
disable_proxy() {
  curl -sf -X PATCH "$TOXI/proxies/$PROXY" -H 'Content-Type: application/json' -d '{"enabled":false}' > /dev/null \
  || curl -sf -X POST "$TOXI/proxies/$PROXY" -H 'Content-Type: application/json' -d '{"enabled":false}' > /dev/null
}

show_status() {
  echo "Service B :";  curl -s "$PAYMENT/admin/config"; echo
  echo "Toxiproxy :";  curl -s "$TOXI/proxies/$PROXY"; echo
}

case "${1:-}" in
  S0)    reset_all;                                          log "S0 applique" ;;
  S1)    reset_all; toxic latence latency '{"latency":500}';  log "S1 applique" ;;
  S2)    reset_all; toxic latence latency '{"latency":2000}'; log "S2 applique" ;;
  S3)    reset_all; errors 0.3;                              log "S3 applique" ;;
  S4)    reset_all; errors 0.7;                              log "S4 applique" ;;
  S5a)   reset_all; disable_proxy;                           log "S5a applique" ;;
  S5b)   reset_all; toxic silence timeout '{"timeout":0}';   log "S5b applique" ;;
  S6)    reset_all;                                          log "S6 debut_normal"
         sleep "$S6_START"
         toxic silence timeout '{"timeout":0}';              log "S6 debut_panne"
         sleep "$S6_DURATION"
         reset_all;                                          log "S6 fin_panne" ;;
  reset) reset_all;                                          log "reset" ;;
  status) show_status ;;
  *) echo "Usage : $0 <S0|S1|S2|S3|S4|S5a|S5b|S6|reset|status>"; exit 1 ;;
esac
