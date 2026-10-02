#!/bin/sh
# Send the pipeline's result to Alertmanager, so a failed build shows up in the
# same place as a failed app.
#   notify_alertmanager.sh firing     a build failed
#   notify_alertmanager.sh resolved   a later build passed
# Uses the variables Jenkins sets for every build (JOB_NAME, BUILD_NUMBER, ...).
set -eu

STATE="${1:-firing}"
AM="${ALERTMANAGER_URL:-http://host.docker.internal:9093}"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "$STATE" = "firing" ]; then
    ENDS=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%M:%SZ)
    SUMMARY="Jenkins build #${BUILD_NUMBER:-?} failed"
else
    # Same labels as the failure alert, so Alertmanager marks that one resolved.
    ENDS="$NOW"
    SUMMARY="Pipeline is green again (build #${BUILD_NUMBER:-?} passed)"
fi

# Escape backslashes and quotes so a commit message can't break the JSON.
SUBJECT=$(printf '%s' "${GIT_SUBJECT:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')

cat > alert.json <<EOF
[{
  "labels": {
    "alertname": "PipelineFailed",
    "severity": "warning",
    "job": "jenkins",
    "pipeline": "${JOB_NAME:-sensor-dashboard-pipeline}"
  },
  "annotations": {
    "summary": "${SUMMARY}",
    "description": "Commit ${GIT_SHORT:-?}: ${SUBJECT}. If it failed after Deploy, the previous build was restored automatically. Console: ${BUILD_URL:-}console"
  },
  "startsAt": "${NOW}",
  "endsAt": "${ENDS}",
  "generatorURL": "${BUILD_URL:-http://localhost}"
}]
EOF

if [ "$STATE" = "firing" ]; then
    echo "Reporting the failed build to Alertmanager at ${AM}"
else
    echo "Telling Alertmanager the pipeline is healthy again"
fi
curl -fsS -X POST -H 'Content-Type: application/json' --data @alert.json "${AM}/api/v2/alerts"
echo
rm -f alert.json
