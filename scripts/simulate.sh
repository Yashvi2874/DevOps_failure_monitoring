#!/bin/sh
# Break (and fix) things during a demo, from bash.
#   scripts/simulate.sh overheat [sensor-1]
#   scripts/simulate.sh offline  [sensor-2]
#   scripts/simulate.sh pollution [sensor-3]
#   scripts/simulate.sh api-errors | crash | reset | status
#   scripts/simulate.sh down | up          stop / start the container
set -eu
URL="${URL:-http://localhost:8000}"
SCENARIO="${1:?usage: simulate.sh <scenario> [sensor]}"
SENSOR="${2:-sensor-1}"

case "$SCENARIO" in
  down)   docker stop sensor-dashboard && echo "Stopped. SensorDashboardDown fires in about 40s." ;;
  up)     docker start sensor-dashboard && echo "Started. The alert resolves within about 30s." ;;
  status) curl -s "$URL/api/simulation"; echo ;;
  overheat|offline|pollution)
          curl -s -X POST "$URL/api/simulate/$SCENARIO" -H 'Content-Type: application/json' \
               -d "{\"sensor\": \"$SENSOR\", \"active\": true}"; echo ;;
  *)      curl -s -X POST "$URL/api/simulate/$SCENARIO" -H 'Content-Type: application/json' \
               -d '{"active": true}'; echo ;;
esac
