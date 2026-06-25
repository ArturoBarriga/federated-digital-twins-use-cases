
# Farm 2 AAS Eclipse BaSyx initialization

set -e

# Configuration
AAS_URL="${AAS_URL:-http://farm2-aas:8081}"
FARM_ID="${FARM_ID:-farm2_aas}"
SHELL_ID="${SHELL_ID:-https://edt.local/aas/farm2_aas}"
SENSORS_SM_ID="${SENSORS_SM_ID:-https://edt.local/aas/farm2_aas/submodels/sensors}"
ACTUATOR_SM_ID="${ACTUATOR_SM_ID:-https://edt.local/aas/farm2_aas/submodels/actuator}"
AREA_HA="${AREA_HA:-30}"
CROP_TYPE="${CROP_TYPE:-barley}"

echo "[$FARM_ID] Initializing BaSyx shell: $SHELL_ID"

# Wait for BaSyx AAS Environment to respond
for i in $(seq 1 30); do
    if curl -sf "$AAS_URL/shells" > /dev/null 2>&1; then
        echo "[$FARM_ID] BaSyx ready"
        break
    fi
    echo "[$FARM_ID] Waiting for BaSyx ($i/30)..."
    sleep 5
done

base64url() { echo -n "$1" | base64 -w0 | tr '+/' '-_' | tr -d '='; }

SHELL_ENC=$(base64url "$SHELL_ID")
SM_SENSORS_ENC=$(base64url "$SENSORS_SM_ID")
SM_ACTUATOR_ENC=$(base64url "$ACTUATOR_SM_ID")

# Step 1: Create AAS shell
echo "[$FARM_ID] Creating shell..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$AAS_URL/shells" \
  -H "Content-Type: application/json" \
  -d "{
    \"idShort\": \"$FARM_ID\",
    \"id\": \"$SHELL_ID\",
    \"assetInformation\": {
      \"assetKind\": \"Instance\",
      \"globalAssetId\": \"$SHELL_ID/asset\"
    }
  }")
if [ "$HTTP_CODE" = "409" ]; then
  echo "[$FARM_ID] Shell already exists"
elif [ "$HTTP_CODE" != "201" ]; then
  echo "[$FARM_ID] Shell creation returned $HTTP_CODE"
fi

# Step 2: Create submodels
create_or_update_submodel() {
  local label="$1"
  local id="$2"
  local encoded="$3"
  local body="$4"

  echo "[$FARM_ID] Creating $label submodel..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$AAS_URL/submodels" \
    -H "Content-Type: application/json" -d "$body")
  if [ "$HTTP_CODE" = "409" ]; then
    echo "[$FARM_ID] $label already exists, updating..."
    curl -s -X PUT "$AAS_URL/submodels/$encoded" \
      -H "Content-Type: application/json" -d "$body" > /dev/null
  elif [ "$HTTP_CODE" != "201" ]; then
    echo "[$FARM_ID] $label creation returned $HTTP_CODE"
  fi
}

# Sensors submodel 
SENSORS_BODY=$(cat <<EOF
{
  "idShort": "sensors",
  "id": "$SENSORS_SM_ID",
  "submodelElements": [
    { "idShort": "humidity_soil_pct",       "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "humidity_pct",            "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "rainfall_mm",             "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "area_ha",                 "modelType": "Property", "valueType": "xs:double", "value": "$AREA_HA" },
    { "idShort": "crop_type",               "modelType": "Property", "valueType": "xs:string", "value": "$CROP_TYPE" },
    { "idShort": "last_updated",            "modelType": "Property", "valueType": "xs:string", "value": "" }
  ]
}
EOF
)

# Actuator submodel
ACTUATOR_BODY=$(cat <<EOF
{
  "idShort": "actuator",
  "id": "$ACTUATOR_SM_ID",
  "submodelElements": [
    { "idShort": "command",         "modelType": "Property", "valueType": "xs:string", "value": "stop" },
    { "idShort": "quota_m3",        "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "valve_open_hours","modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "valid_from",      "modelType": "Property", "valueType": "xs:string", "value": "" },
    { "idShort": "valid_until",     "modelType": "Property", "valueType": "xs:string", "value": "" },
    { "idShort": "acknowledged",    "modelType": "Property", "valueType": "xs:boolean", "value": "false" }
  ]
}
EOF
)

create_or_update_submodel "sensors"   "$SENSORS_SM_ID"  "$SM_SENSORS_ENC"  "$SENSORS_BODY"
create_or_update_submodel "actuator"  "$ACTUATOR_SM_ID" "$SM_ACTUATOR_ENC" "$ACTUATOR_BODY"

# Step 3: Link submodels to shell
echo "[$FARM_ID] Linking submodels to shell..."

existing_refs=$(curl -s "$AAS_URL/shells/$SHELL_ENC/submodel-refs")
ref_exists() {
  local target="$1"
  echo "$existing_refs" | grep -q "\"value\":\"$target\""
}

link_ref() {
  local sm_id="$1"
  if ! ref_exists "$sm_id"; then
    echo "  Adding reference to $sm_id..."
    curl -s -X POST "$AAS_URL/shells/$SHELL_ENC/submodel-refs" \
      -H "Content-Type: application/json" \
      -d "{
        \"type\": \"MODEL_REFERENCE\",
        \"keys\": [{ \"type\": \"Submodel\", \"value\": \"$sm_id\" }]
      }" > /dev/null
  else
    echo "  Reference to $sm_id already exists"
  fi
}

link_ref "$SENSORS_SM_ID"
link_ref "$ACTUATOR_SM_ID"

echo "[$FARM_ID] Initialization complete"