import sys
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from shared.models import NormalizedFarmData, ActuatorCommand

NGSILD_URL = os.getenv("NGSILD_URL", "http://farm3-ngsild-server:1026")
FARM_ID = os.getenv("FARM_ID", "farm3_ngsild")
ENTITY_ID = os.getenv("ENTITY_ID", "urn:ngsi-ld:Farm:farm3")
ADAPTER_PORT = int(os.getenv("ADAPTER_PORT", "8001"))


def _get_val(attr):
    if isinstance(attr, dict):
        return attr.get("value", attr)
    return attr

# NGSI-LD adapter for Farm 3, on-demand REST servr
class NGSILDAdapter:
    def __init__(self):
        self._entity_url = f"{NGSILD_URL}/ngsi-ld/v1/entities/{ENTITY_ID}"
        self._attrs_url = f"{self._entity_url}/attrs/"

    def read_sensors(self) -> NormalizedFarmData | None:
        try:
            r = requests.get(self._entity_url, timeout=10)
            if r.status_code != 200:
                return None
            entity = r.json()
            ts = _get_val(entity.get("last_updated", ""))
            if not ts:
                return None
            data = NormalizedFarmData(
                farm_id=FARM_ID,
                timestamp=ts,
                soil_humidity_40cm_pct=float(_get_val(entity.get("moisture_pct", 0))),
                rainfall_mm=float(_get_val(entity.get("rainfall_mm", 0))),
                area_ha=float(_get_val(entity.get("area_ha", 0))),
                crop_type=str(_get_val(entity.get("crop_type", ""))),
                temperature_c=float(_get_val(entity.get("temperature_c", 0))),
                wind_direction=float(_get_val(entity.get("wind_direction", 0))),
                wind_speed=float(_get_val(entity.get("wind_speed", 0))),
            )
            print(f"[NGSILDAdapter] Read sensors: moisture_pct={data.soil_humidity_40cm_pct}%, temperature_c={data.temperature_c}C, rainfall_mm={data.rainfall_mm}mm")
            return data
        except Exception as e:
            print(f"[NGSILDAdapter] read failed: {e}")
            return None

    # Write irrigation command to NGSI-LD actuator
    def write_command_to_twin(self, cmd: ActuatorCommand):
        attrs = {
            "command": {"type": "Property", "value": cmd.command},
            "quota_m3": {"type": "Property", "value": cmd.quota_m3},
            "valve_open_hours": {"type": "Property", "value": cmd.valve_open_hours},
            "valid_from": {"type": "Property", "value": cmd.valid_from.isoformat() if hasattr(cmd.valid_from, "isoformat") else str(cmd.valid_from)},
            "valid_until": {"type": "Property", "value": cmd.valid_until.isoformat() if hasattr(cmd.valid_until, "isoformat") else str(cmd.valid_until)},
            "acknowledged": {"type": "Property", "value": False},
        }
        try:
            r = requests.patch(self._attrs_url, json=attrs, timeout=10)
            r.raise_for_status()
            print(f"[NGSILDAdapter] Command written to {FARM_ID}: {cmd.quota_m3}m3")
        except Exception as e:
            print(f"[NGSILDAdapter] command write failed: {e}")


# HTTP request handler for NGSI-LD adapter endpoints
class RequestHandler(BaseHTTPRequestHandler):
    adapter: NGSILDAdapter = None

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
        print(f"[NGSILDAdapter] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    adapter = NGSILDAdapter()
    RequestHandler.adapter = adapter
    server = HTTPServer(("0.0.0.0", ADAPTER_PORT), RequestHandler)
    print(f"[NGSILDAdapter] Listening on port {ADAPTER_PORT}, waiting for central manager requests")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
