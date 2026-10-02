#!/bin/sh
# Called by Jenkins when the smoke test fails. Puts the last image that passed
# a smoke test (tagged sensor-dashboard:stable) back into service.
set -u

if ! docker image inspect sensor-dashboard:stable >/dev/null 2>&1; then
    echo "Smoke test failed and there is no earlier good build to roll back to."
    exit 0
fi

echo "Smoke test failed. Rolling back to the last good build (sensor-dashboard:stable)..."
IMAGE_TAG=stable FORCE_UNHEALTHY=false docker compose up -d --no-build dashboard

# Check that the old build really is serving again.
if docker run --rm -i --network sensor-net -e EXPECTED_BUILD= -e SMOKE_TIMEOUT=60 \
        sensor-dashboard:stable python - < scripts/smoke_test.py; then
    echo "Rollback complete: the previous build is serving traffic again."
else
    echo "Rollback finished but the old build is not healthy either. Needs a human."
fi
