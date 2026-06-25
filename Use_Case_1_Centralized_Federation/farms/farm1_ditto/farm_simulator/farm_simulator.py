
# Eclipse Ditto farm simulator for Farm 1 (wheat, 50 ha)
# Extends FarmSimulator and implements push_telemetry() and check_actuator_commands() 

import sys
import os
import requests
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from farm_base.farm_simulator import FarmSimulator

DITTO_URL = os.getenv("DITTO_URL", "http://farm1-ditto-gateway:8080")
FARM_ID = os.getenv("FARM_ID", "farm1_ditto")
THING_ID = os.getenv("THING_ID", "edt:farm1")
AREA_HA = float(os.getenv("AREA_HA", "50"))
CROP_TYPE = os.getenv("CROP_TYPE", "wheat")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "60"))


class Farm1DittoSimulator(FarmSimulator):
    def __init__(self):
        super().__init__(FARM_ID, AREA_HA, CROP_TYPE)
        self._headers = {"x-ditto-pre-authenticated": "nginx:ditto"}
        self._thing_url = f"{DITTO_URL}/api/2/things/{THING_ID}"
        self._wait_for_ditto()

    # Wait for Ditto Gatewaay
    def _wait_for_ditto(self, retries=30, delay=5):
        for i in range(retries):
            try:
                r = requests.get(
                    f"{DITTO_URL}/api/2/things", headers=self._headers, timeout=10
                )
                if r.status_code < 500:
                    print(f"[{FARM_ID}] Ditto ready")
                    return
            except (requests.ConnectionError, requests.ReadTimeout):
                pass
            print(f"[{FARM_ID}] Waiting for Ditto ({i+1}/{retries})...")
            time.sleep(delay)
        print(f"[{FARM_ID}] Ditto not available, continuing anyway")

    def push_telemetry(self, telemetry: dict):
        feature = {
            "properties": {
                "soil_moisture_pct": telemetry["soil_humidity_40cm_pct"],
                "temperature_c": telemetry["weather"]["temperature_c"],
                "rainfall_mm": telemetry["weather"]["rainfall_mm"],
                "last_updated": telemetry["timestamp"],
            }
        }
        url = f"{self._thing_url}/features/sensors"
        try:
            r = requests.put(url, json=feature, headers=self._headers, timeout=10)
            r.raise_for_status()
            print(f"[{FARM_ID}] Sent telemetry: soil_moisture_pct={telemetry['soil_humidity_40cm_pct']}%, temperature_c={telemetry['weather']['temperature_c']}C, rainfall_mm={telemetry['weather']['rainfall_mm']}mm")
        except Exception as e:
            print(f"[{FARM_ID}] push failed: {e}")

    def check_actuator_commands(self) -> list:
        url = f"{self._thing_url}/features/actuator"
        try:
            r = requests.get(url, headers=self._headers, timeout=10)
            if r.status_code == 200:
                props = r.json().get("properties", {})
                # Only accept a command that hasn't been acknowledged yet
                if props.get("command") == "irrigate" and not props.get(
                    "acknowledged", False
                ):
                    cmd = {
                        "command": "irrigate",
                        "quota_m3": props.get("quota_m3", 0),
                        "valve_open_hours": props.get("valve_open_hours", 0),
                    }
                    print(f"[{FARM_ID}] Received irrigation command: {cmd['quota_m3']}m3 over {cmd['valve_open_hours']}h")
                    # Mark acknowledged so we don't re-process it
                    requests.put(
                        url + "/properties/acknowledged",
                        json=True,
                        headers=self._headers,
                        timeout=10,
                    )
                    return [cmd]
        except Exception as e:
            print(f"[{FARM_ID}] command check failed: {e}")
        return []

if __name__ == "__main__":
    sim = Farm1DittoSimulator()
    try:
        sim.run_loop(POLL_INTERVAL)
    except KeyboardInterrupt:
        sim.stop()
