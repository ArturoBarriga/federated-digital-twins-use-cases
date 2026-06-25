# Synthetic leaf sensor data generator.
#
# Each tree runs one instance. It:
#   1. Generates sensor data
#   2. Pushes readings to its own tree's BaSyx AAS server
#   3. Exposes /inject_anomaly and /clear_anomaly to enable testing
#

import os
import random
import time
import threading
import urllib.parse
from datetime import datetime, timezone
import requests
from flask import Flask, jsonify, request

SIMULATOR_PORT = int(os.environ.get("SIMULATOR_PORT", "5012"))
INTERVAL_MINUTES = int(os.environ.get("SAMPLE_RATE_MINUTES", "1"))
DT_ID = os.environ.get("DT_ID", "dt_01")
AAS_URL = os.environ.get("AAS_URL", "http://localhost:4001")
SHELL_ID = f"https://edt.local/aas/{DT_ID}"
SHELL_ENC = urllib.parse.quote(SHELL_ID, safe="")
SM_ID = f"https://edt.local/aas/{DT_ID}/submodels/leaf_measurement"
SM_IDSHORT = "LeafMeasurement"
SUBMODEL_URL = f"{AAS_URL}/aasServer/shells/{SHELL_ENC}/aas/submodels/{SM_IDSHORT}"
BASYX_HEADERS = {"Host": "localhost"}

app = Flask(__name__)

# Simulates leaf turgor pressure and temperature
# Each tree starts with slightly different baselines
class SimulatedLeaf:
    def __init__(self):
        self._turgor_kPa = 1.2 
        self._turgor_kPa += random.uniform(-0.3, 0.3)
        self._temp = 25.0 
        self._temp += random.uniform(-2, 2)
        self._anomaly_override = None
        self._running = True

    # Advance one time step with diurnal factor
    def step(self):
        hour = datetime.now(timezone.utc).hour
        is_daytime = 6 <= hour <= 18
        
        # Turgor: higher during day
        if is_daytime:
            self._turgor_kPa += random.uniform(0.02, 0.08)
        else:
            self._turgor_kPa -= random.uniform(0.02, 0.06)
        self._turgor_kPa = max(0.5, min(2.2, self._turgor_kPa))
        
        # Temperature: warmer during day
        if is_daytime:
            self._temp += random.uniform(0.1, 0.5)
        else:
            self._temp -= random.uniform(0.1, 0.3)
        self._temp = max(8, min(42, self._temp))

        if self._anomaly_override is not None:
            self._turgor_kPa = self._anomaly_override

        return self._turgor_kPa, self._temp

    # Generate one reading and PUT the submodel
    def push(self):
        turgor, temp = self.step()
        ts = datetime.now(timezone.utc).isoformat()
        sm = {
            "idShort": SM_IDSHORT,
            "identification": {"id": SM_ID, "idType": "IRI"},
            "kind": "Instance",
            "submodelElements": [
                {"idShort": "turgor_pressure_kPa",
                 "modelType": {"name": "Property"},
                 "valueType": "xs:double", "value": str(round(turgor, 4))},
                {"idShort": "leaf_temperature",
                 "modelType": {"name": "Property"},
                 "valueType": "xs:double", "value": str(round(temp, 1))},
                {"idShort": "last_updated",
                 "modelType": {"name": "Property"},
                 "valueType": "xs:string", "value": ts},
            ],
        }
        try:
            r = requests.put(SUBMODEL_URL, json=sm, timeout=10, headers=BASYX_HEADERS)
            print(
                f"[{DT_ID}Sim][{ts}] Pushed to BaSyx ({SUBMODEL_URL}): "
                f"turgor={turgor:.4f}, temp={temp:.1f} (HTTP {r.status_code})",
                flush=True,
            )
        except Exception as e:
            print(f"[{DT_ID}Sim][{ts}] Push error: {e}", flush=True)

    # Continuous loop: push readings every INTERVAL_MINUTES
    def run_loop(self):
        print(
            f"[{DT_ID}Sim] Starting (interval={INTERVAL_MINUTES}min, "
            f"BaSyx={AAS_URL})",
            flush=True,
        )
        while self._running:
            self.push()
            time.sleep(INTERVAL_MINUTES * 60)

    # Override turgor with an extreme value for synthetic fault injection
    def inject_anomaly(self, value):
        self._anomaly_override = value
        print(f"[{DT_ID}Sim] Anomaly injected: turgor={value} kPa", flush=True)

    # Remove the anomaly override and reset to a random normal value
    def clear_anomaly(self):
        self._anomaly_override = None
        self._turgor_kPa = 1.2 
        self._turgor_kPa += random.uniform(-0.3, 0.3)
        self._temp = 25.0 
        self._temp += random.uniform(-2, 2)
        print(f"[{DT_ID}Sim] Anomaly cleared, reset to normal", flush=True)

    def stop(self):
        self._running = False

sim = SimulatedLeaf()

# HTTP endpoints

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"dt_id": DT_ID, "status": "running"})


@app.route("/inject_anomaly", methods=["POST"])
def inject_anomaly():
    data = request.get_json(force=True, silent=True)
    if data and "turgor_pressure_kPa" in data:
        sim.inject_anomaly(float(data["turgor_pressure_kPa"]))
        return jsonify({"status": "anomaly_injected", "value": data["turgor_pressure_kPa"]})
    return jsonify({"error": "missing turgor_pressure_kPa"}), 400


@app.route("/clear_anomaly", methods=["POST"])
def clear_anomaly():
    sim.clear_anomaly()
    return jsonify({"status": "anomaly_cleared"})


@app.route("/stop", methods=["POST"])
def stop_sim():
    sim.stop()
    return jsonify({"status": "stopped"})


if __name__ == "__main__":
    threading.Thread(target=sim.run_loop, daemon=True).start()
    print(f"[{DT_ID}Sim]   SIMULATOR STARTED", flush=True)
    print(f"[{DT_ID}Sim]   Tree: {DT_ID}", flush=True)
    print(f"[{DT_ID}Sim]   Target BaSyx: {SUBMODEL_URL}", flush=True)
    app.run(host="0.0.0.0", port=SIMULATOR_PORT, debug=False)
