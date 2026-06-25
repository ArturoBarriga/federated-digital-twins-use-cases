
# Manages the lifecycle of a sprinkler:


import os
import base64
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "5004"))
AAS_URL = os.environ.get("AAS_URL", "http://sprinkler-aas:8081")
SM_ID = "https://edt.local/aas/sprinkler_dt/submodels/sprinkler_control"
SM_ENC = base64.urlsafe_b64encode(SM_ID.encode()).decode().rstrip("=")

app = Flask(__name__)
_state = {"state": "idle", "flow_rate": "0", "start_time": "", "total_volume": "0"}

def _patch_property(name: str, value: str):
    try:
        url = f"{AAS_URL}/submodels/{SM_ENC}/submodel-elements/{name}/$value"
        requests.patch(url, json=value, timeout=5)
    except requests.RequestException:
        pass


# Transition sprinkler to active state at the given flow rate (L/min)
def _do_start(flow: float = 50.0):
    now = datetime.now(timezone.utc).isoformat()
    _state["state"] = "active"
    _state["flow_rate"] = str(flow)
    _state["start_time"] = now
    _patch_property("state", "active")
    _patch_property("flow_rate", str(flow))
    _patch_property("start_time", now)


# Transition sprinkler to idle
def _do_stop():
    start_str = _state["start_time"]
    flow = float(_state["flow_rate"] or 0)
    now = datetime.now(timezone.utc)
    elapsed_hours = 0
    if start_str:
        try:
            start_dt = datetime.fromisoformat(start_str)
            elapsed_hours = (now - start_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            pass
    added_volume = flow * elapsed_hours
    prev_volume = float(_state["total_volume"] or 0)
    total = prev_volume + added_volume
    _state["total_volume"] = str(total)
    _state["state"] = "idle"
    _state["flow_rate"] = "0"
    _patch_property("total_volume", str(total))
    _patch_property("state", "idle")
    _patch_property("flow_rate", "0")


def _op_var(value, value_type):
    return {"value": {"modelType": "Property", "valueType": value_type, "value": value}}


def _extract_input(body):
    if isinstance(body, dict):
        return body.get("inputArguments", [])
    return body if isinstance(body, list) else []


def _get_val(arg):
    v = arg.get("value", {})
    if isinstance(v, dict):
        return v.get("value")
    return v


# BaSyx operation delegation: start irrigation with an optional flow rate
@app.route("/invoke/start", methods=["POST"])
def invoke_start():
    body = request.get_json(silent=True) or {}
    input_args = _extract_input(body)
    flow = 50.0
    for arg in input_args:
        val = _get_val(arg)
        if val is not None:
            try:
                flow = float(val)
            except (ValueError, TypeError):
                pass
    _do_start(flow)
    return jsonify([
        _op_var("active", "xs:string"),
        _op_var(str(flow), "xs:double"),
    ])


@app.route("/invoke/stop", methods=["POST"])
def invoke_stop():
    _do_stop()
    return jsonify([
        _op_var("idle", "xs:string"),
        _op_var("0", "xs:double"),
        _op_var(_state["total_volume"], "xs:double"),
    ])


@app.route("/start", methods=["POST"])
def start_route():
    body = request.get_json(silent=True) or {}
    flow = body.get("flow_rate", 50.0)
    _do_start(flow)
    return jsonify({"state": "active", "flow_rate": flow, "start_time": _state["start_time"], "message": "Irrigation started"})


@app.route("/stop", methods=["POST"])
def stop_route():
    _do_stop()
    return jsonify({
        "state": "idle",
        "volume_added": 0,
        "total_volume": _state["total_volume"],
        "message": "Irrigation stopped",
    })


@app.route("/status", methods=["GET"])
def status():
    return jsonify(_state)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False)
