set -e
AAS_URL="${AAS_URL:-http://tree1_aas:4001}"
DT_ID="${DT_ID:-dt_01}"
SHELL_ID="${SHELL_ID:-https://edt.local/aas/$DT_ID}"
SM_ID="${SM_ID:-https://edt.local/aas/$DT_ID/submodels/leaf_measurement}"
SM_IDSHORT="LeafMeasurement"
HOST_HDR="localhost"
CURL="curl -s -H \"Host: $HOST_HDR\""

echo "[$DT_ID] Initializing BaSyx shell: $SHELL_ID"

urlenc() { echo -n "$1" | sed 's/%/%25/g; s/:/%3A/g; s/\//%2F/g'; }

SHELL_ENC=$(urlenc "$SHELL_ID")

# Wait for BaSyx
for i in $(seq 1 30); do
    if eval "$CURL \"$AAS_URL/aasServer/shells\"" > /dev/null 2>&1; then break; fi
    echo "[$DT_ID] Waiting for BaSyx ($i/30)..."
    sleep 5
done

# Create Shell
echo "[$DT_ID] Creating shell..."
SHELL_BODY=$(cat <<EOF
{
  "idShort": "${DT_ID}",
  "identification": {"id": "${SHELL_ID}", "idType": "IRI"},
  "asset": {
    "idShort": "asset_${DT_ID}",
    "identification": {"id": "${SHELL_ID}/asset", "idType": "IRI"},
    "kind": "Instance"
  }
}
EOF
)
HTTP_CODE=$(echo "$SHELL_BODY" | eval "$CURL -o /dev/null -w '%{http_code}' -X PUT \
  \"$AAS_URL/aasServer/shells/$SHELL_ENC\" \
  -H 'Content-Type: application/json' -d @-")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  echo "[$DT_ID] Shell created/updated (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" = "409" ]; then
  echo "[$DT_ID] Shell already exists"
else
  echo "[$DT_ID] Shell creation returned HTTP $HTTP_CODE"
fi

# Create Submodel
SM_BODY=$(cat <<EOF
{
  "idShort": "${SM_IDSHORT}",
  "identification": {"id": "${SM_ID}", "idType": "IRI"},
  "kind": "Instance",
  "submodelElements": [
    {"idShort": "turgor_pressure_kPa",  "modelType": {"name": "Property"}, "valueType": "xs:double", "value": "0"},
    {"idShort": "leaf_temperature",      "modelType": {"name": "Property"}, "valueType": "xs:double", "value": "0"},
    {"idShort": "last_updated",          "modelType": {"name": "Property"}, "valueType": "xs:string", "value": ""}
  ]
}
EOF
)

echo "[$DT_ID] Creating submodel..."
HTTP_CODE=$(echo "$SM_BODY" | eval "$CURL -o /dev/null -w '%{http_code}' -X PUT \
  \"$AAS_URL/aasServer/shells/$SHELL_ENC/aas/submodels/$SM_IDSHORT\" \
  -H 'Content-Type: application/json' -d @-")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  echo "[$DT_ID] Submodel created/updated (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" = "409" ]; then
  echo "[$DT_ID] Submodel already exists"
else
  echo "[$DT_ID] Submodel creation returned HTTP $HTTP_CODE"
fi

echo "[$DT_ID] Initialization complete"
