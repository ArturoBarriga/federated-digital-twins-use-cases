#!/bin/bash
set -e

AAS_URL="${AAS_URL:-http://leaf-aas:8081}"
DT_ID="${DT_ID:-leaf_dt}"
SHELL_ID="${SHELL_ID:-https://edt.local/aas/leaf_dt}"
SM_ID="${SM_ID:-https://edt.local/aas/leaf_dt/submodels/leaf_measurement}"

echo "[$DT_ID] Initializing BaSyx shell: $SHELL_ID"

for i in $(seq 1 30); do
    if curl -sf "$AAS_URL/shells" > /dev/null 2>&1; then break; fi
    echo "[$DT_ID] Waiting for BaSyx ($i/30)..."
    sleep 5
done

base64url() { echo -n "$1" | base64 -w0 | tr '+/' '-_' | tr -d '='; }

SHELL_ENC=$(base64url "$SHELL_ID")
SM_ENC=$(base64url "$SM_ID")

echo "[$DT_ID] Creating shell..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$AAS_URL/shells" \
  -H "Content-Type: application/json" \
  -d "{
    \"idShort\": \"$DT_ID\",
    \"id\": \"$SHELL_ID\",
    \"assetInformation\": {
      \"assetKind\": \"Instance\",
      \"globalAssetId\": \"$SHELL_ID/asset\"
    }
  }")
if [ "$HTTP_CODE" = "409" ]; then
  echo "[$DT_ID] Shell already exists"
elif [ "$HTTP_CODE" != "201" ]; then
  echo "[$DT_ID] Shell creation returned $HTTP_CODE"
fi

SM_BODY=$(cat <<EOF
{
  "idShort": "LeafMeasurement",
  "id": "$SM_ID",
  "submodelElements": [
    { "idShort": "turgor_pressure_kPa",  "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "leaf_temperature",      "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "canopy_humidity",       "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "stomatal_conductance",  "modelType": "Property", "valueType": "xs:double", "value": "0" },
    { "idShort": "last_updated",          "modelType": "Property", "valueType": "xs:string", "value": "" }
  ]
}
EOF
)

echo "[$DT_ID] Creating submodel..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$AAS_URL/submodels" \
  -H "Content-Type: application/json" -d "$SM_BODY")
if [ "$HTTP_CODE" = "409" ]; then
  echo "[$DT_ID] Submodel already exists, updating..."
  curl -s -X PUT "$AAS_URL/submodels/$SM_ENC" \
    -H "Content-Type: application/json" -d "$SM_BODY" > /dev/null
elif [ "$HTTP_CODE" != "201" ]; then
  echo "[$DT_ID] Submodel creation returned $HTTP_CODE"
fi

echo "[$DT_ID] Linking submodel to shell..."
existing_refs=$(curl -s "$AAS_URL/shells/$SHELL_ENC/submodel-refs")
if ! echo "$existing_refs" | grep -q "\"value\":\"$SM_ID\""; then
  curl -s -X POST "$AAS_URL/shells/$SHELL_ENC/submodel-refs" \
    -H "Content-Type: application/json" \
    -d "{
      \"type\": \"MODEL_REFERENCE\",
      \"keys\": [{ \"type\": \"Submodel\", \"value\": \"$SM_ID\" }]
    }" > /dev/null
fi

echo "[$DT_ID] Initialization complete"
