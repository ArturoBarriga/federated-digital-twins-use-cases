
# Generates realistic diurnal patterns for four leaf physiological variables:
#  - turgor_pressure_kPa:  leaf turgor pressure 
#  - leaf_temperature:      leaf temperature 
#  - canopy_humidity:       canopy relative humidity 
#  - stomatal_conductance:  stomatal conductance

import os
import random
import base64
import time
from datetime import datetime, timezone
import requests
from flask import Flask, jsonify

SIMULATOR_PORT = int(os.environ.get('SIMULATOR_PORT', '5012'))
INTERVAL_MINUTES = int(os.environ.get('SAMPLE_RATE_MINUTES', '1'))
AAS_URL = os.environ.get('AAS_URL', 'http://leaf-aas:8081')
SM_ID = "https://edt.local/aas/leaf_dt/submodels/leaf_measurement"
SM_ENC = base64.urlsafe_b64encode(SM_ID.encode()).decode().rstrip("=")
SUBMODEL_URL = f"{AAS_URL}/submodels/{SM_ENC}"

app = Flask(__name__)

# Simulates leaf turgor, temperature, humidiity, and conductance sensors
class SimulatedLeaf:

    def __init__(self):
        self._turgor_kPa = 1.2
        self._temp = 25.0
        self._humidity = 65.0
        self._conductance = 0.5
        self._running = True

    # Advance simulated values
    def step(self):
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        current_hour = now.hour

        # Simulate higher values during the day
        is_daytime = 6 <= current_hour <= 18
        if is_daytime:
            day_factor = 1.3
        else:
            day_factor = 0.85

        previous_turgor_kPa = self._turgor_kPa
        previous_temperature = self._temp
        previous_humidity = self._humidity
        previous_conductance = self._conductance

        # Update leaf turgor pressure
        turgor_variation = random.uniform(-0.05, 0.05)
        adjusted_turgor_variation = turgor_variation * day_factor
        new_turgor_kPa = self._turgor_kPa + adjusted_turgor_variation
        if new_turgor_kPa < 0.0:
            new_turgor_kPa = 0.0
        elif new_turgor_kPa > 2.5:
            new_turgor_kPa = 2.5
        self._turgor_kPa = new_turgor_kPa

        # Update leaf temperature
        temperature_variation = random.uniform(-1, 1)
        adjusted_temperature_variation = temperature_variation * day_factor
        new_temperature = self._temp + adjusted_temperature_variation
        if new_temperature < 10:
            new_temperature = 10
        elif new_temperature > 45:
            new_temperature = 45
        self._temp = new_temperature

        # Update canopy humidity
        humidity_variation = random.uniform(-3, 3)
        new_humidity = self._humidity + humidity_variation
        if new_humidity < 30:
            new_humidity = 30
        elif new_humidity > 100:
            new_humidity = 100
        self._humidity = new_humidity

        # Update stomatal conductance
        conductance_variation = random.uniform(-0.05, 0.05)
        adjusted_conductance_variation = conductance_variation * day_factor
        new_conductance = self._conductance + adjusted_conductance_variation
        if new_conductance < 0.0:
            new_conductance = 0.0
        elif new_conductance > 1.0:
            new_conductance = 1.0
        self._conductance = new_conductance

        self.push()


    def _build_submodel(self):
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "idShort": "LeafMeasurement",
            "id": SM_ID,
            "submodelElements": [
                {
                    "idShort": "turgor_pressure_kPa",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._turgor_kPa, 4)),
                },
                {
                    "idShort": "leaf_temperature",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._temp, 1)),
                },
                {
                    "idShort": "canopy_humidity",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._humidity, 1)),
                },
                {
                    "idShort": "stomatal_conductance",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._conductance, 4)),
                },
                {
                    "idShort": "last_updated",
                    "modelType": "Property",
                    "valueType": "xs:string",
                    "value": ts,
                },
            ],
        }

    # Send the complete submodel to the Leaf AAS server via PUT
    def push(self):
        body = self._build_submodel()
        ts = datetime.now(timezone.utc).isoformat()
        values = {e["idShort"]: e["value"] for e in body["submodelElements"]}
        print(f"[LeafSim][{datetime.now(timezone.utc).isoformat()}] "
              f"Pushing submodel to {SUBMODEL_URL}: {values}", flush=True)
        try:
            r = requests.put(SUBMODEL_URL, json=body, timeout=10)
            if r.ok:
                print(f"[LeafSim][{ts}] PUT OK (HTTP {r.status_code})", flush=True)
            else:
                print(f"[LeafSim][{ts}] PUT failed: HTTP {r.status_code} {r.text[:200]}", flush=True)
        except requests.RequestException as e:
            print(f"[LeafSim][{ts}] PUT error: {e}", flush=True)

    def run_loop(self):
        print(f"[LeafSim][{datetime.now(timezone.utc).isoformat()}] Starting simulation loop (interval={INTERVAL_MINUTES}min)", flush=True)
        self.push()
        while self._running:
            time.sleep(INTERVAL_MINUTES * 60)
            self.step()

    def stop(self):
        self._running = False


if __name__ == '__main__':
    sim = SimulatedLeaf()
    import threading
    threading.Thread(target=sim.run_loop, daemon=True).start()

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok"})

    print(f"[LeafSim][{datetime.now(timezone.utc).isoformat()}] Starting Flask on port {SIMULATOR_PORT}, pushing to {SUBMODEL_URL}", flush=True)
    app.run(host='0.0.0.0', port=SIMULATOR_PORT, debug=False)
