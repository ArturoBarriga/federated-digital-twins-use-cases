
# Generates realistic diurnal patterns for two trunk physiological variables:
#  - diameter_mm:  trunk diameter
#  - sap_flow_rate: sap flow

import os
import random
import base64
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify

SIMULATOR_PORT = int(os.environ.get('SIMULATOR_PORT', '5011'))
INTERVAL_MINUTES = int(os.environ.get('SAMPLE_RATE_MINUTES', '1'))
AAS_URL = os.environ.get('AAS_URL', 'http://trunk-aas:8081')
SM_ID = "https://edt.local/aas/trunk_dt/submodels/trunk_measurement"
SM_ENC = base64.urlsafe_b64encode(SM_ID.encode()).decode().rstrip("=")
SUBMODEL_URL = f"{AAS_URL}/submodels/{SM_ENC}"

app = Flask(__name__)

# Simulates trunk dendometer and sap-flow sensor readings
class SimulatedTrunk:

    def __init__(self):
        self._diameter_mm = 145.0
        self._sap_flow = 25.0
        self._running = True

    # Advance simulated values by one sample interval
    def step(self):
        # Current timestamp
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        current_hour = now.hour

        # Higher values during the day
        is_daytime = 6 <= current_hour <= 18
        if is_daytime:
            day_factor = 1.3
        else:
            day_factor = 0.85

        # Store previous values
        previous_diameter_mm = self._diameter_mm
        previous_sap_flow = self._sap_flow

        # Update trunk diameter
        diameter_variation = random.uniform(-0.3, 0.3)
        adjusted_diameter_variation = diameter_variation * day_factor
        new_diameter_mm = self._diameter_mm + adjusted_diameter_variation
        # Keep diameter within realistic bounds
        if new_diameter_mm < 130:
            new_diameter_mm = 130
        elif new_diameter_mm > 160:
            new_diameter_mm = 160
        self._diameter_mm = new_diameter_mm

        # Update sap flow
        sap_flow_variation = random.uniform(-2, 2)
        adjusted_sap_flow_variation = sap_flow_variation * day_factor
        new_sap_flow = self._sap_flow + adjusted_sap_flow_variation
        # Keep sap flow within realistic bounds
        if new_sap_flow < 0:
            new_sap_flow = 0
        elif new_sap_flow > 50:
            new_sap_flow = 50
        self._sap_flow = new_sap_flow

        # Push the updated values
        self.push()


    def _build_submodel(self):
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "idShort": "TrunkMeasurement",
            "id": SM_ID,
            "submodelElements": [
                {
                    "idShort": "diameter_mm",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._diameter_mm, 4)),
                },
                {
                    "idShort": "sap_flow_rate",
                    "modelType": "Property",
                    "valueType": "xs:double",
                    "value": str(round(self._sap_flow, 2)),
                },
                {
                    "idShort": "last_updated",
                    "modelType": "Property",
                    "valueType": "xs:string",
                    "value": ts,
                },
            ],
        }

    # Send the complete submodel to the Trunk AAS server via PUT
    def push(self):
        body = self._build_submodel()
        ts = datetime.now(timezone.utc).isoformat()

        print(f"[TrunkSim][{datetime.now(timezone.utc).isoformat()}] "
              f"Pushing submodel to {SUBMODEL_URL}: "
              f"diameter_mm={body['submodelElements'][0]['value']}, "
              f"sap_flow_rate={body['submodelElements'][1]['value']}", flush=True)
        try:
            r = requests.put(SUBMODEL_URL, json=body, timeout=10)
            if r.ok:
                print(f"[TrunkSim][{ts}] PUT OK (HTTP {r.status_code})", flush=True)
            else:
                print(f"[TrunkSim][{ts}] PUT failed: HTTP {r.status_code} {r.text[:200]}", flush=True)
        except requests.RequestException as e:
            print(f"[TrunkSim][{ts}] PUT error: {e}", flush=True)


    def run_loop(self):
        print(f"[TrunkSim][{datetime.now(timezone.utc).isoformat()}] Starting simulation loop (interval={INTERVAL_MINUTES}min)", flush=True)
        self.push()
        while self._running:
            time.sleep(INTERVAL_MINUTES * 60)
            self.step()

    def stop(self):
        self._running = False


if __name__ == '__main__':
    sim = SimulatedTrunk()
    import threading
    threading.Thread(target=sim.run_loop, daemon=True).start()

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok"})

    print(f"[TrunkSim][{datetime.now(timezone.utc).isoformat()}] Starting Flask on port {SIMULATOR_PORT}, pushing to {SUBMODEL_URL}", flush=True)
    app.run(host='0.0.0.0', port=SIMULATOR_PORT, debug=False)
