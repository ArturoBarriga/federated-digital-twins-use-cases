
import sys
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from shared.models import NormalizedFarmData, ActuatorCommand

DITTO_URL = os.getenv("DITTO_URL", "http://farm1-ditto-gateway:8080")
THING_ID = os.getenv("THING_ID", "edt:farm1")
FARM_ID = os.getenv("FARM_ID", "farm1_ditto")
ADAPTER_PORT = int(os.getenv("ADAPTER_PORT", "8001"))

# Ditto adapter for Farm 1, on-demand REST server.
class DittoAdapter:
    def __init__(self):
        self._headers = {"x-ditto-pre-authenticated": "nginx:ditto"}
        self._thing_url = f"{DITTO_URL}/api/2/things/{THING_ID}"

    # Fetch latest sensor readings from Ditto Thing
    def read_sensors(self) -> NormalizedFarmData | None:
        try:
            r = requests.get(self._thing_url, headers=self._headers, timeout=10)
            if r.status_code != 200:
                return None
            body = r.json()
            attrs = body.get("attributes", {})
            props = body.get("features", {}).get("sensors", {}).get("properties", {})
            ts = props.get("last_updated", "")
            if not ts:
                return None
            data = NormalizedFarmData(
                farm_id=FARM_ID,
                timestamp=ts,
                soil_humidity_40cm_pct=props.get("soil_moisture_pct", 0),
                rainfall_mm=props.get("rainfall_mm", 0),
                area_ha=attrs.get("area_ha", 0),
                crop_type=attrs.get("crop_type", ""),
                temperature_c=props.get("temperature_c", 0),
                wind_direction=props.get("wind_direction", 0),
                wind_speed=props.get("wind_speed", 0),
            )
            print(f"[DittoAdapter] Read sensors: soil_moisture_pct={data.soil_humidity_40cm_pct}%, temperature_c={data.temperature_c}C, rainfall_mm={data.rainfall_mm}mm")
            return data
        except Exception as e:
            print(f"[DittoAdapter] read failed: {e}")
            return None

    # Write irrigation command to Ditto actuator feature
    def write_command_to_twin(self, cmd: ActuatorCommand):
        feature = {
            "properties": {
                "command": cmd.command,
                "quota_m3": cmd.quota_m3,
                "valve_open_hours": cmd.valve_open_hours,
                "valid_from": (
                    cmd.valid_from.isoformat()
                    if hasattr(cmd.valid_from, "isoformat")
                    else cmd.valid_from
                ),
                "valid_until": (
                    cmd.valid_until.isoformat()
                    if hasattr(cmd.valid_until, "isoformat")
                    else cmd.valid_until
                ),
                "acknowledged": False,
            }
        }
        url = f"{self._thing_url}/features/actuator"
        try:
            r = requests.put(url, json=feature, headers=self._headers, timeout=10)
            r.raise_for_status()
            print(f"[DittoAdapter] Command written to {FARM_ID}: {cmd.quota_m3}m3")
        except Exception as e:
            print(f"[DittoAdapter] command write failed: {e}")


# HTTP request handler for Ditto adapter endpoints
class RequestHandler(BaseHTTPRequestHandler):
    adapter: DittoAdapter = None

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
        print(f"[DittoAdapter] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    adapter = DittoAdapter()
    RequestHandler.adapter = adapter
    server = HTTPServer(("0.0.0.0", ADAPTER_PORT), RequestHandler)
    print(f"[DittoAdapter] Listening on port {ADAPTER_PORT}, waiting for central manager requests")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
