
#  - Runs a background scheduler thread that triggers the Tree DT assess
#    operation once per day at a configurable hour (default 08:00 UTC).
#  - If the Tree DT returns a severe stress classification (2), automatically
#    invokes the Sprinkler DT start operation to begin irrigation.
#  - Exposes REST endpoints for manual trigger and state inspection.

import os
import base64
import threading
import time
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "5005"))
STRESS_AAS_URL = os.environ.get("STRESS_AAS_URL", "http://tree-aas:8081")
IRRIGATION_AAS_URL = os.environ.get("IRRIGATION_AAS_URL", "http://sprinkler-aas:8081")
SCHEDULED_HOUR = int(os.environ.get("SCHEDULED_HOUR", "8"))
TREE_SM_ID = "https://edt.local/aas/tree_dt/submodels/water_stress_assessment"
SPRINKLER_SM_ID = "https://edt.local/aas/sprinkler_dt/submodels/sprinkler_control"

TREE_ASSESS_URL = (
    f"{STRESS_AAS_URL}/submodels/"
    f"{base64.urlsafe_b64encode(TREE_SM_ID.encode()).decode().rstrip('=')}/"
    f"submodel-elements/assess/invoke"
)
SPRINKLER_START_URL = (
    f"{IRRIGATION_AAS_URL}/submodels/"
    f"{base64.urlsafe_b64encode(SPRINKLER_SM_ID.encode()).decode().rstrip('=')}/"
    f"submodel-elements/start/invoke"
)

app = Flask(__name__)

_state = {"state": "monitoring", "tree_count": "1", "last_assessment_result": ""}
_triggered_today = False


def _sm_prop(value, value_type):
    return {"modelType": "Property", "valueType": value_type, "value": value}


def _op_var(value, value_type):
    return {"value": _sm_prop(value, value_type)}

# Run a full assessment cycle: 1) invoke Tree DT, 2) check result, and 3) irrigate if severe.
def _do_assessment():
    global _state
    print(f"[Farm] Assessment started", flush=True)
    try:
        resp = requests.post(TREE_ASSESS_URL, json={}, timeout=60)
        if resp.status_code != 200:
            print(f"[Farm] Tree assess failed: {resp.text}", flush=True)
            return None
        result = resp.json()
        if not result.get("success"):
            print(f"[Farm] Tree assess execution failed: {result}", flush=True)
            return None
        stress = int(result["outputArguments"][0]["value"]["value"])
        _state["last_assessment_result"] = str(result)

        # Only severe stress (2) triggers irrigation
        if stress == 2:
            spr_body = {"inputArguments": [{"value": _sm_prop("50", "xs:double")}]}
            spr = requests.post(SPRINKLER_START_URL, json=spr_body, timeout=10)
            if spr.status_code == 200:
                _state["state"] = "irrigating"
                print(f"[Farm] Sprinkler started (stress=severe)", flush=True)
            else:
                print(f"[Farm] Sprinkler start failed: {spr.text}", flush=True)
        else:
            _state["state"] = "monitoring"
            print(f"[Farm] No action needed (stress={stress})", flush=True)
        return stress
    except requests.RequestException as e:
        print(f"[Farm] Assessment error: {e}", flush=True)
        return None


# BaSyx operation delegation endpoint for manual triggering
@app.route("/invoke/trigger", methods=["POST"])
def invoke_trigger():
    stress = _do_assessment()
    if stress is None:
        return jsonify([_op_var("-1", "xs:int")])
    return jsonify([_op_var(str(stress), "xs:int")])


# Convenience REST endpoint (bypasses BaSyx delegation)
@app.route("/trigger", methods=["POST"])
def trigger_route():
    stress = _do_assessment()
    if stress is None:
        return jsonify({"error": "Assessment failed"})
    return jsonify({
        "action": "irrigation_started" if stress == 2 else "no_action",
        "stress_classification": stress,
        "state": _state["state"],
    })


@app.route("/state", methods=["GET"])
def state():
    return jsonify(_state)


def _scheduler_loop():
    global _triggered_today
    print(f"[Farm] Scheduler: daily at {SCHEDULED_HOUR}:00 UTC", flush=True)
    while True:
        now = datetime.now(timezone.utc)
        if now.hour == SCHEDULED_HOUR and not _triggered_today:
            _triggered_today = True
            _do_assessment()
        if now.hour != SCHEDULED_HOUR:
            _triggered_today = False
        time.sleep(30)


if __name__ == "__main__":
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False)
