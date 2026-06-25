
# Farm 1 Eclipse Ditto initialization

set -e

# Configuration 
DITTO_URL="${DITTO_URL:-http://farm1-ditto-gateway:8080}"
THING_ID="${THING_ID:-edt.farm1}"
FARM_ID="${FARM_ID:-farm1_ditto}"
AREA_HA="${AREA_HA:-50}"
CROP_TYPE="${CROP_TYPE:-wheat}"

echo "[$FARM_ID] Initializing Ditto thing: $THING_ID"

# Wait for Ditto Gateway to respond
for i in $(seq 1 30); do
    if curl -sf -H "x-ditto-pre-authenticated: nginx:ditto" "$DITTO_URL/api/2/things" > /dev/null 2>&1; then
        echo "[$FARM_ID] Ditto is ready"
        break
    fi
    echo "[$FARM_ID] Waiting for Ditto ($i/30)..."
    sleep 5
done

# Step 1: Create Policy
POLICY_ID="${THING_ID//./:}:policy"
POLICY_BODY=$(cat <<EOF
{
  "entries": {
    "DEFAULT": {
      "subjects": {
        "nginx:ditto": { "type": "nginx basic auth" }
      },
      "resources": {
        "thing:/":   { "grant": ["READ", "WRITE"], "revoke": [] },
        "policy:/":  { "grant": ["READ", "WRITE"], "revoke": [] },
        "message:/": { "grant": ["READ", "WRITE"], "revoke": [] }
      }
    }
  }
}
EOF
)

echo "[$FARM_ID] Creating policy..."
curl -s -X PUT \
  -H "x-ditto-pre-authenticated: nginx:ditto" \
  -H "Content-Type: application/json" \
  "$DITTO_URL/api/2/policies/$POLICY_ID" \
  -d "$POLICY_BODY"

# Step 2: Create Thing with features
THING_BODY=$(cat <<EOF
{
  "policyId": "$POLICY_ID",
  "attributes": {
    "farm_id": "$FARM_ID",
    "description": "Digital Twin for $FARM_ID",
    "area_ha": $AREA_HA,
    "crop_type": "$CROP_TYPE"
  },
  "features": {
    "sensors": {
      "properties": {
        "soil_moisture_pct": 0,
        "temperature_c": 0,
        "rainfall_mm": 0,
        "last_updated": ""
      }
    },
    "actuator": {
      "properties": {
        "command": "stop",
        "quota_m3": 0,
        "valve_open_hours": 0,
        "valid_from": "",
        "valid_until": "",
        "acknowledged": false
      }
    }
  }
}
EOF
)

echo "[$FARM_ID] Creating thing..."
curl -s -X PUT \
  -H "x-ditto-pre-authenticated: nginx:ditto" \
  -H "Content-Type: application/json" \
  "$DITTO_URL/api/2/things/$THING_ID" \
  -d "$THING_BODY"

echo "[$FARM_ID] Initialization complete"
