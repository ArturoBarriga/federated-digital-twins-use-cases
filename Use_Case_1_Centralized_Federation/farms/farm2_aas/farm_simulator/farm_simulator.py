
# AAS farm simulator for Farm 2 (barley, 30 ha) using Eclipse BaSyx
# Extends FarmSimulator and implements push_telemetry() and  check_actuator_commands() 

import sys
import os
import base64
import requests
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from farm_base.farm_simulator import FarmSimulator

AAS_URL = os.getenv("AAS_URL", "http://farm2-aas:8081")
FARM_ID = os.getenv("FARM_ID", "farm2_aas")
SENSORS_SM_ID = os.getenv("SENSORS_SM_ID", "https://edt.local/aas/farm2_aas/submodels/sensors")
ACTUATOR_SM_ID = os.getenv("ACTUATOR_SM_ID", "https://edt.local/aas/farm2_aas/submodels/actuator")
AREA_HA = float(os.getenv("AREA_HA", "30"))
CROP_TYPE = os.getenv("CROP_TYPE", "barley")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "60"))

# BaSyx requires URL-safe base64 encoding (without padding)
def _encode_id(id_str: str) -> str:
    return base64.urlsafe_b64encode(id_str.encode()).decode().rstrip("=")


class Farm2AASSimulator(FarmSimulator):
    def __init__(self):
        super().__init__(FARM_ID, AREA_HA, CROP_TYPE)
        self._sensors_url = f"{AAS_URL}/submodels/{_encode_id(SENSORS_SM_ID)}"
        self._actuator_url = f"{AAS_URL}/submodels/{_encode_id(ACTUATOR_SM_ID)}"
        self._wait_for_aas()

    def _wait_for_aas(self, retries=30, delay=5):
        for i in range(retries):
            try:
                r = requests.get(f"{AAS_URL}/shells", timeout=10)
                if r.status_code < 500:
                    print(f"[{FARM_ID}] BaSyx ready")
                    return
            except (requests.ConnectionError, requests.ReadTimeout):
                pass
            print(f"[{FARM_ID}] Waiting for BaSyx ({i+1}/{retries})...")
            time.sleep(delay)
        print(f"[{FARM_ID}] BaSyx not available, continuing anyway")

    def push_telemetry(self, telemetry: dict):
        body = {
            "idShort": "sensors",
            "id": SENSORS_SM_ID,
            "submodelElements": [
                {"idShort": "humidity_soil_pct",      "modelType": "Property", "valueType": "xs:double", "value": str(telemetry["soil_humidity_40cm_pct"])},
                {"idShort": "humidity_pct",           "modelType": "Property", "valueType": "xs:double", "value": str(telemetry["weather"]["humidity_pct"])},
                {"idShort": "rainfall_mm",            "modelType": "Property", "valueType": "xs:double", "value": str(telemetry["weather"]["rainfall_mm"])},
                {"idShort": "area_ha",                "modelType": "Property", "valueType": "xs:double", "value": str(self.area_ha)},
                {"idShort": "crop_type",              "modelType": "Property", "valueType": "xs:string", "value": self.crop_type},
                {"idShort": "last_updated",           "modelType": "Property", "valueType": "xs:string", "value": telemetry["timestamp"]},
            ],
        }
        try:
            r = requests.put(self._sensors_url, json=body, timeout=10)
            r.raise_for_status()
            print(f"[{FARM_ID}] Sent telemetry: humidity_soil_pct={telemetry['soil_humidity_40cm_pct']}%, humidity_pct={telemetry['weather']['humidity_pct']}%, rainfall_mm={telemetry['weather']['rainfall_mm']}mm")
        except Exception as e:
            print(f"[{FARM_ID}] push failed: {e}")

    def check_actuator_commands(self) -> list:
        try:
            r = requests.get(self._actuator_url, timeout=10)
            if r.status_code == 200:
                sm = r.json()
                props = {}
                submodel_elements = sm.get("submodelElements", [])
                for e in submodel_elements:
                    id_short = e["idShort"]
                    value = e.get("value")
                    props[id_short] = value
                if props.get("command") == "irrigate" and props.get("acknowledged") != "true":
                    cmd = {
                        "command": "irrigate",
                        "quota_m3": float(props.get("quota_m3", 0)),
                        "valve_open_hours": float(props.get("valve_open_hours", 0)),
                    }
                    # Mark acknowledged 
                    ack_body = {"idShort": "acknowledged", "modelType": "Property", "valueType": "xs:boolean", "value": "true"}
                    requests.put(f"{self._actuator_url}/submodel-elements/acknowledged", json=ack_body, timeout=10)
                    return [cmd]
        except Exception as e:
            print(f"[{FARM_ID}] command check failed: {e}")
        return []


if __name__ == "__main__":
    sim = Farm2AASSimulator()
    try:
        sim.run_loop(POLL_INTERVAL)
    except KeyboardInterrupt:
        sim.stop()
