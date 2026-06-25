
# Farm 3 AAS  NGSI-LD entity initialization

set -e

# Configuration
NGSILD_URL="${NGSILD_URL:-http://farm3-ngsild-server:1026}"
FARM_ID="${FARM_ID:-farm3_ngsild}"
ENTITY_ID="${ENTITY_ID:-urn:ngsi-ld:Farm:farm3}"
AREA_HA="${AREA_HA:-20}"
CROP_TYPE="${CROP_TYPE:-maize}"

echo "[$FARM_ID] Initializing NGSI-LD entity: $ENTITY_ID"

# Wait for Orion-LD to respond
for i in $(seq 1 30); do
    if curl -sf "$NGSILD_URL/ngsi-ld/v1/entities/?type=Farm" > /dev/null 2>&1; then
        echo "[$FARM_ID] Orion-LD ready"
        break
    fi
    echo "[$FARM_ID] Waiting for Orion-LD ($i/30)..."
    sleep 5
done

# Create the NGSI-LD entity with initial property values
NGSLD_ENTITY=$(cat <<EOF
{
  "id": "$ENTITY_ID",
  "type": "Farm",
  "area_ha": { "type": "Property", "value": $AREA_HA },
  "crop_type": { "type": "Property", "value": "$CROP_TYPE" },
  "moisture_pct": { "type": "Property", "value": 0 },
  "rainfall_mm": { "type": "Property", "value": 0 },
  "wind_direction": { "type": "Property", "value": 0 },
  "wind_speed": { "type": "Property", "value": 0 },
  "temperature_c": { "type": "Property", "value": 0 },
  "last_updated": { "type": "Property", "value": "" },
  "command": { "type": "Property", "value": "stop" },
  "quota_m3": { "type": "Property", "value": 0 },
  "valve_open_hours": { "type": "Property", "value": 0 },
  "valid_from": { "type": "Property", "value": "" },
  "valid_until": { "type": "Property", "value": "" },
  "acknowledged": { "type": "Property", "value": false }
}
EOF
)

echo "[$FARM_ID] Creating NGSI-LD entity..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$NGSILD_URL/ngsi-ld/v1/entities/" \
  -H "Content-Type: application/json" -d "$NGSLD_ENTITY")
if [ "$HTTP_CODE" = "409" ]; then
    echo "[$FARM_ID] Entity already exists, updating properties..."
    curl -s -X PATCH "$NGSILD_URL/ngsi-ld/v1/entities/$ENTITY_ID/attrs/" \
      -H "Content-Type: application/json" \
      -d '{
        "area_ha": { "type": "Property", "value": '"$AREA_HA"' },
        "crop_type": { "type": "Property", "value": "'"$CROP_TYPE"'" },
        "command": { "type": "Property", "value": "stop" },
        "quota_m3": { "type": "Property", "value": 0 },
        "valve_open_hours": { "type": "Property", "value": 0 },
        "acknowledged": { "type": "Property", "value": false }
      }' > /dev/null
elif [ "$HTTP_CODE" != "201" ]; then
    echo "[$FARM_ID] Entity creation returned $HTTP_CODE"
fi

echo "[$FARM_ID] Initialization complete"
