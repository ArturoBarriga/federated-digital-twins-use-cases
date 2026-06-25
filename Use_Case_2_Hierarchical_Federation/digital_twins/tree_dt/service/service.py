
#  1. Fetches current sensor values from Leaf DT and Trunk DT AAS shells
#  2. Sends raw values to the preprocessor microservice for min-max normalisation
#  3. Sends the normalised array to the ML model microservice for classification
#  4. Writes the result (stress_classification, water_stress_index, timestamp)
#     back to the Tree DT AAS submodel

import os
import base64
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "5003"))
AAS_URL = os.environ.get("AAS_URL", "http://tree-aas:8081")
TRUNK_AAS_URL = os.environ.get("TRUNK_AAS_URL", "http://trunk-aas:8081")
LEAF_AAS_URL = os.environ.get("LEAF_AAS_URL", "http://leaf-aas:8081")
PREPROCESSOR_URL = os.environ.get("PREPROCESSOR_URL", "http://tree-data-preprocessor:8000")
ML_MODEL_URL = os.environ.get("ML_MODEL_URL", "http://tree-ml-model:8000")
SM_ID = "https://edt.local/aas/tree_dt/submodels/water_stress_assessment"
SM_ENC = base64.urlsafe_b64encode(SM_ID.encode()).decode().rstrip("=")
TRUNK_SM_ID = "https://edt.local/aas/trunk_dt/submodels/trunk_measurement"
TRUNK_SM_ENC = base64.urlsafe_b64encode(TRUNK_SM_ID.encode()).decode().rstrip("=")
LEAF_SM_ID = "https://edt.local/aas/leaf_dt/submodels/leaf_measurement"
LEAF_SM_ENC = base64.urlsafe_b64encode(LEAF_SM_ID.encode()).decode().rstrip("=")

app = Flask(__name__)

def _ts():
    return datetime.now(timezone.utc).isoformat()


def _patch_property(name: str, value: str):
    try:
        url = f"{AAS_URL}/submodels/{SM_ENC}/submodel-elements/{name}/$value"
        r = requests.patch(url, json=value, timeout=5)
        if r.ok:
            print(f"[TreeService][{_ts()}] PATCH {name} = {value} OK (HTTP {r.status_code})", flush=True)
        else:
            print(f"[TreeService][{_ts()}] PATCH {name} failed: {r.status_code} {r.text[:100]}", flush=True)
    except requests.RequestException as e:
        print(f"[TreeService][{_ts()}] PATCH {name} error: {e}", flush=True)


def _get_aas_value(aas_url, sm_enc, prop):
    try:
        url = f"{aas_url}/submodels/{sm_enc}/submodel-elements/{prop}/$value"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            val = r.text.strip().strip('"')
            print(f"[TreeService][{_ts()}] GET {prop} from {aas_url}: \"{val}\"", flush=True)
            return val
        else:
            print(f"[TreeService][{_ts()}] GET {prop} failed: {r.status_code} {r.text[:100]}", flush=True)
    except requests.RequestException as e:
        print(f"[TreeService][{_ts()}] GET {prop} error: {e}", flush=True)
    return None


def _sm_element_raw(value, value_type):
    return {"value": {"modelType": "Property", "valueType": value_type, "value": value}}


# Core assess pipeline: 1) fetch, 2) preprocess, 3) classify, and 4) persist
def assess_handler():
    t0 = datetime.now(timezone.utc)
    print(f"[TreeService][{_ts()}] Assess pipeline STARTED", flush=True)

    # 1. Fetch current sensor values from Leaf DT and Trunk DT
    print(f"[TreeService][{_ts()}] Step 1/4: Fetching sensor values from Leaf&Trunk AAS", flush=True)
    leaf_turgor = _get_aas_value(LEAF_AAS_URL, LEAF_SM_ENC, "turgor_pressure_kPa")
    leaf_temp = _get_aas_value(LEAF_AAS_URL, LEAF_SM_ENC, "leaf_temperature")
    canopy_humidity = _get_aas_value(LEAF_AAS_URL, LEAF_SM_ENC, "canopy_humidity")
    stomatal_conductance = _get_aas_value(LEAF_AAS_URL, LEAF_SM_ENC, "stomatal_conductance")
    sap_flow_rate = _get_aas_value(TRUNK_AAS_URL, TRUNK_SM_ENC, "sap_flow_rate")
    trunk_size = _get_aas_value(TRUNK_AAS_URL, TRUNK_SM_ENC, "diameter_mm")

    raw_values = [leaf_turgor, leaf_temp, canopy_humidity, stomatal_conductance, sap_flow_rate, trunk_size]
    print(f"[TreeService][{_ts()}] Raw sensor values: {raw_values}", flush=True)

    if not all(raw_values):
        missing = [n for n, v in zip(
            ["turgor", "temp", "humidity", "conductance", "sap_flow", "trunk_size"], raw_values
        ) if not v]
        return [_sm_element_raw("-1", "xs:int")]

    raw_payload = {
        "leaf_turgor_pressure_kPa": leaf_turgor,
        "leaf_temperature": leaf_temp,
        "canopy_humidity": canopy_humidity,
        "stomatal_conductance": stomatal_conductance,
        "sap_flow_rate": sap_flow_rate,
        "trunk_size": trunk_size,
    }
    print(f"[TreeService][{_ts()}] Step 2/4: Sending to preprocessor {PREPROCESSOR_URL}/preprocess", flush=True)

    # 2. Send raw values to the preprocessor microservice (min-max normalisation)
    try:
        pp_resp = requests.post(f"{PREPROCESSOR_URL}/preprocess", json=raw_payload, timeout=10)
        if pp_resp.status_code != 200:
            print(f"[TreeService][{_ts()}] Preprocessor returned {pp_resp.status_code}: {pp_resp.text[:200]}", flush=True)
            return [_sm_element_raw("-1", "xs:int")]
        pp_json = pp_resp.json()
        print(f"[TreeService][{_ts()}] Preprocessor response: {pp_json}", flush=True)
    except requests.RequestException as e:
        print(f"[TreeService][{_ts()}] Preprocessor request error: {e}", flush=True)
        return [_sm_element_raw("-1", "xs:int")]

    model_input = pp_json.get("modelInput")
    if not model_input:
        return [_sm_element_raw("-1", "xs:int")]

    print(f"[TreeService][{_ts()}] Step 3/4: Sending to ML model {ML_MODEL_URL}/predict", flush=True)
    print(f"[TreeService][{_ts()}] Normalised input: {model_input}", flush=True)

    # 3. Send preprocessed array to the ML model microservice for classification
    try:
        ml_resp = requests.post(f"{ML_MODEL_URL}/predict", json={"modelInput": model_input}, timeout=10)
        if ml_resp.status_code != 200:
            return [_sm_element_raw("-1", "xs:int")]
        ml_json = ml_resp.json()
        print(f"[TreeService][{_ts()}] ML model response: {ml_json}", flush=True)
    except requests.RequestException as e:
        print(f"[TreeService][{_ts()}] ML model request error: {e}", flush=True)
        return [_sm_element_raw("-1", "xs:int")]

    result = ml_resp.json()
    label_str = result.get("output", "")
    stress_map = {"No stress (0)": 0, "Mid stress (1)": 1, "Severe stress (2)": 2}
    stress_idx = stress_map.get(label_str, -1)
    now = datetime.now(timezone.utc).isoformat()

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[TreeService][{_ts()}] Step 4/4: Classified as \"{label_str}\" stress={stress_idx}  (took {elapsed:.2f}s)", flush=True)

    # 4. Persist classification back to the Tree AAS submodel
    _state["stress_classification"] = str(stress_idx)
    _state["water_stress_index"] = str(float(stress_idx))
    _state["last_assessment_time"] = now

    print(f"[TreeService][{_ts()}] Persisting results to Tree AAS...", flush=True)
    _patch_property("stress_classification", str(stress_idx))
    _patch_property("water_stress_index", str(float(stress_idx)))
    _patch_property("last_assessment_time", now)

    print(f"[TreeService][{_ts()}] Assess pipeline COMPLETE (stress={stress_idx})", flush=True)
    return [_sm_element_raw(str(stress_idx), "xs:int")]


# BaSyx operation delegation endpoint — called by the Tree AAS server
@app.route("/invoke/assess", methods=["POST"])
def invoke_assess():
    print(f"[TreeService][{_ts()}] >>> /invoke/assess CALLED from {request.remote_addr}", flush=True)
    try:
        result = assess_handler()
        print(f"[TreeService][{_ts()}] >>> /invoke/assess returning: {result}", flush=True)
        return jsonify(result)
    except Exception as e:
        print(f"[TreeService][{_ts()}] >>> /invoke/assess EXCEPTION: {e}", flush=True)
        return jsonify([{"value": str(e), "valueType": "xs:string"}])


# Convenience REST endpoint (bypasses BaSyx delegation)
@app.route("/assess", methods=["POST"])
def assess():
    print(f"[TreeService][{_ts()}] >>> /assess CALLED from {request.remote_addr}", flush=True)
    output = assess_handler()
    stress = int(output[0]["value"]["value"]) if output else -1
    label_map = ["No stress (0)", "Mid stress (1)", "Severe stress (2)"]
    resp = {
        "stress_classification": stress,
        "label": label_map[stress] if 0 <= stress <= 2 else "Unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(f"[TreeService][{_ts()}] >>> /assess response: {resp}", flush=True)
    return jsonify(resp)


if __name__ == "__main__":
    print(f"[TreeService][{_ts()}] Starting on port {SERVICE_PORT}", flush=True)
    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False)
