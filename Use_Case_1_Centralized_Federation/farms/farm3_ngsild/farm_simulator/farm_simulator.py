
# NGSI-LD farm simulator for Farm 3 (maize, 20 ha)
# Extends FarmSimulator and implements push_telemetry() and  check_actuator_commands() 

import sys
import os
import requests
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from farm_base.farm_simulator import FarmSimulator

NGSILD_URL = os.getenv("NGSILD_URL", "http://farm3-ngsild-server:1026")
FARM_ID = os.getenv("FARM_ID", "farm3_ngsild")
ENTITY_ID = os.getenv("ENTITY_ID", "urn:ngsi-ld:Farm:farm3")
AREA_HA = float(os.getenv("AREA_HA", "20"))
CROP_TYPE = os.getenv("CROP_TYPE", "maize")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "60"))

# Extract value from NGSI-LD attribute
def _get_ngsi_value(attr):
    if isinstance(attr, dict):
        return attr.get("value", 0)
    return attr

class Farm3NGSILDSimulator(FarmSimulator):
    def __init__(self):
        super().__init__(FARM_ID, AREA_HA, CROP_TYPE)
        # NGSI-LD uses two endpoints: /attrs for patching, /entities for reading
        self._attrs_url = f"{NGSILD_URL}/ngsi-ld/v1/entities/{ENTITY_ID}/attrs/"
        self._entity_url = f"{NGSILD_URL}/ngsi-ld/v1/entities/{ENTITY_ID}"
        self._wait_for_ngsild()

    def _wait_for_ngsild(self, retries=30, delay=5):
        for i in range(retries):
            try:
                r = requests.get(f"{NGSILD_URL}/ngsi-ld/v1/entities/?type=Farm", timeout=10)
                if r.status_code < 500:
                    print(f"[{FARM_ID}] Orion-LD ready")
                    return
            except (requests.ConnectionError, requests.ReadTimeout):
                pass
            print(f"[{FARM_ID}] Waiting for Orion-LD ({i+1}/{retries})...")
            time.sleep(delay)
        print(f"[{FARM_ID}] Orion-LD not available, continuing anyway")

    def push_telemetry(self, telemetry: dict):
        # Build NGSI-LD attributes for soil and weather sensors
        attrs = {
            "moisture_pct": {"type": "Property", "value": telemetry["soil_humidity_40cm_pct"]},
            "rainfall_mm": {"type": "Property", "value": telemetry["weather"]["rainfall_mm"]},
            "wind_direction": {"type": "Property", "value": telemetry["weather"]["wind_direction"]},
            "wind_speed": {"type": "Property", "value": telemetry["weather"]["wind_speed"]},
            "temperature_c": {"type": "Property", "value": telemetry["weather"]["temperature_c"]},
            "last_updated": {"type": "Property", "value": telemetry["timestamp"]},
        }
        try:
            r = requests.patch(self._attrs_url, json=attrs, timeout=10)
            r.raise_for_status()
            moisture = telemetry['soil_humidity_40cm_pct']
            rain = telemetry['weather']['rainfall_mm']
            print(f"[{FARM_ID}] Telemetry: moisture_pct={moisture}%, rainfall_mm={rain}mm")
        except Exception as e:
            print(f"[{FARM_ID}] push failed: {e}")

    def check_actuator_commands(self) -> list:
        try:
            r = requests.get(self._entity_url, timeout=10)
            if r.status_code == 200:
                entity = r.json()
                # Extract command and acknowledged values (NGSI-LD format variations)
                cmd_attr = entity.get("command", {})
                if isinstance(cmd_attr, dict):
                    cmd_val = cmd_attr.get("value", "")
                else:
                    cmd_val = cmd_attr
                ack_attr = entity.get("acknowledged", {})
                if isinstance(ack_attr, dict):
                    ack_val = ack_attr.get("value", False)
                else:
                    ack_val = ack_attr
                # Check for new irrigatrion command (not yet acknowledged)
                if cmd_val == "irrigate" and not ack_val:
                    cmd = {
                        "command": "irrigate",
                        "quota_m3": float(_get_ngsi_value(entity.get("quota_m3", 0))),
                        "valve_open_hours": float(_get_ngsi_value(entity.get("valve_open_hours", 0))),
                    }
                    # Mark command as acknowledged
                    ack_body = {"acknowledged": {"type": "Property", "value": True}}
                    requests.patch(self._attrs_url, json=ack_body, timeout=10)
                    return [cmd]
        except Exception as e:
            print(f"[{FARM_ID}] command check failed: {e}")
        return []


if __name__ == "__main__":
    sim = Farm3NGSILDSimulator()
    try:
        sim.run_loop(POLL_INTERVAL)
    except KeyboardInterrupt:
        sim.stop()
