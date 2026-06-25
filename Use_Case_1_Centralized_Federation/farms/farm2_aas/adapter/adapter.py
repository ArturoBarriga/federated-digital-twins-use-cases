
import sys
import os
import json
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from shared.models import NormalizedFarmData, ActuatorCommand

AAS_URL = os.getenv("AAS_URL", "http://farm2-aas:8081")
FARM_ID = os.getenv("FARM_ID", "farm2_aas")
SENSORS_SM_ID = os.getenv("SENSORS_SM_ID", "https://edt.local/aas/farm2_aas/submodels/sensors")
ACTUATOR_SM_ID = os.getenv("ACTUATOR_SM_ID", "https://edt.local/aas/farm2_aas/submodels/actuator")
ADAPTER_PORT = int(os.getenv("ADAPTER_PORT", "8001"))


def _encode_id(id_str: str) -> str:
    return base64.urlsafe_b64encode(id_str.encode()).decode().rstrip("=")

# AAS adapter for Farm 2, on-demand REST server.
class AASAdapter:
    def __init__(self):
        self._sensors_url = f"{AAS_URL}/submodels/{_encode_id(SENSORS_SM_ID)}"
        self._actuator_url = f"{AAS_URL}/submodels/{_encode_id(ACTUATOR_SM_ID)}"

    # Fetch latest sensor readings from AAS
    def read_sensors(self) -> NormalizedFarmData | None:
        try:
            r = requests.get(self._sensors_url, timeout=10)
            if r.status_code != 200:
                return None
            sm = r.json()
            props = {}
            submodel_elements = sm.get("submodelElements", [])

            for e in submodel_elements:
                id_short = e["idShort"]
                value = e.get("value", "")
                props[id_short] = value

            ts = props.get("last_updated", "")
            if not ts:
                return None
            data = NormalizedFarmData(
                farm_id=FARM_ID,
                timestamp=ts,
                soil_humidity_40cm_pct=float(props.get("humidity_soil_pct", 0)),
                rainfall_mm=float(props.get("rainfall_mm", 0)),
                area_ha=float(props.get("area_ha", 0)),
                crop_type=props.get("crop_type", ""),
                temperature_c=float(props.get("temperature_c", 0)),
                wind_direction=float(props.get("wind_direction", 0)),
                wind_speed=float(props.get("wind_speed", 0)),
            )
            print(f"[AASAdapter] Read sensors: humidity_soil_pct={data.soil_humidity_40cm_pct}%, temperature_c={data.temperature_c}C, rainfall_mm={data.rainfall_mm}mm")
            return data
        except Exception as e:
            print(f"[AASAdapter] read failed: {e}")
            return None

    # Write irrigation command to AAS actuator feature
    def write_command_to_twin(self, cmd: ActuatorCommand):
        body = {
            "idShort": "actuator",
            "id": ACTUATOR_SM_ID,
            "submodelElements": [
                {"idShort": "command",          "modelType": "Property", "valueType": "xs:string",  "value": cmd.command},
                {"idShort": "quota_m3",         "modelType": "Property", "valueType": "xs:double",  "value": str(cmd.quota_m3)},
                {"idShort": "valve_open_hours", "modelType": "Property", "valueType": "xs:double",  "value": str(cmd.valve_open_hours)},
                {"idShort": "valid_from",       "modelType": "Property", "valueType": "xs:string",  "value": cmd.valid_from.isoformat() if hasattr(cmd.valid_from, "isoformat") else str(cmd.valid_from)},
                {"idShort": "valid_until",      "modelType": "Property", "valueType": "xs:string",  "value": cmd.valid_until.isoformat() if hasattr(cmd.valid_until, "isoformat") else str(cmd.valid_until)},
                {"idShort": "acknowledged",     "modelType": "Property", "valueType": "xs:boolean", "value": "false"},
            ],
        }
        try:
            r = requests.put(self._actuator_url, json=body, timeout=10)
            r.raise_for_status()
            print(f"[AASAdapter] Command written to {FARM_ID}: {cmd.quota_m3}m3")
        except Exception as e:
            print(f"[AASAdapter] command write failed: {e}")

# HTTP request handler for AAS adapter endpoints
class RequestHandler(BaseHTTPRequestHandler):
    adapter: AASAdapter = None

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/telemetry":
            data = self.adapter.read_sensors()
            if data:
                self._send_json(200, data.model_dump(mode="json"))
            else:
                self._send_json(503, {"error": "sensor data unavailable"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/command":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            cmd = ActuatorCommand(**body)
            self.adapter.write_command_to_twin(cmd)
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"[AASAdapter] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    adapter = AASAdapter()
    RequestHandler.adapter = adapter
    server = HTTPServer(("0.0.0.0", ADAPTER_PORT), RequestHandler)
    print(f"[AASAdapter] Listening on port {ADAPTER_PORT}, waiting for central manager requests")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
