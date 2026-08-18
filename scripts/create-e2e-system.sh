#!/usr/bin/env bash
#
# Create the system row the smoke tests need, unless one already exists.
#
# The mock seeder writes production against an existing system, so a fresh
# database has to be given one first. The values are the ones the Setup page
# would send, with a manual irradiance source: the seeder writes its own
# irradiance rows, and manual keeps a CI run from reaching out to NASA POWER.
#
# Usage: API_URL=http://localhost:8000 ./scripts/create-e2e-system.sh
#
# Exit codes: 1 if the API never becomes reachable, or if creation is rejected.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
HEALTH_ATTEMPTS=30

for attempt in $(seq "$HEALTH_ATTEMPTS"); do
  if curl -fsS "$API_URL/api/health" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq "$HEALTH_ATTEMPTS" ]; then
    echo "The API at $API_URL did not become reachable." >&2
    exit 1
  fi
  sleep 2
done

# A 200 means a system is already configured. Overwriting it would throw away
# whatever the developer set up on the Setup tab.
if curl -fsS "$API_URL/api/settings" >/dev/null 2>&1; then
  echo "A system is already configured - leaving it as it is."
  exit 0
fi

curl -fsS -X POST "$API_URL/api/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "enphase_system_id": "e2e-smoke",
    "name": "Smoke Test Array",
    "location": "Portland, OR",
    "latitude": "45.5231",
    "longitude": "-122.6765",
    "system_size_kw": "10.5",
    "panel_count": 30,
    "panel_wattage_w": 350,
    "install_date": "2021-06-01",
    "tilt_angle_deg": "30",
    "azimuth_deg": "180",
    "degradation_rate": "0.5",
    "warranty_degradation_rate": "0.7",
    "energy_rate_per_kwh": "0.12",
    "energy_rate_currency": "USD",
    "irradiance_source": "manual"
  }' >/dev/null

echo "Created the smoke test system. Seed it next: make seed-mock"
