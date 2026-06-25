
#   Implementation of the DT logic:
#   1. Periodically reads its own sensor data from its tree's BaSyx server
#   2. Discovers peer DTs via HTTP heartbeats
#   3. Reads peer sensor data
#   4. Runs a local anomaly detection algorithm comparing the measurements
#   5. Exposes /anomaly, /peers, /topology, /logs
#

import os
import json
import time
import threading
import math
import logging
import urllib.parse
from datetime import datetime, timezone
import yaml
import requests
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dt_logic")

DT_ID = os.environ.get("DT_ID", "dt_01")
AAS_URL = os.environ.get("AAS_URL", "http://localhost:4001")
DT_PORT = int(os.environ.get("DT_PORT", "8000"))
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
BASYX_SUFFIX = os.environ.get("BASYX_SUFFIX", "aas")
DT_SUFFIX = os.environ.get("DT_SUFFIX", "logic")
SHELL_ID = f"https://edt.local/aas/{DT_ID}"
SM_ID = f"https://edt.local/aas/{DT_ID}/submodels/leaf_measurement"
SM_IDSHORT = "LeafMeasurement"
SHELL_ENC = urllib.parse.quote(SHELL_ID, safe="")
BAXYX_HEADERS = {"Host": "localhost"}

config = {}                    # runtime configuration (loaded from YAML)
peers = {}                     # registered peers: { dt_id: {host, port, last_seen} }
anomaly_flags = []             # history of anomaly detections
decision_log = []              # every anomaly check result
_cached_readings = {           # latest readings fetched from own BaSyx
    "turgor_pressure_kPa": 0.0,
    "leaf_temperature": 0.0,
    "last_updated": "",
}
running = True           


# Hostname helpers 
def basyx_host(pid):
    num = int(pid.split("_")[1])
    return f"tree{num}_{BASYX_SUFFIX}"

def dt_host(pid):
    num = int(pid.split("_")[1])
    return f"tree{num}_{DT_SUFFIX}"


# Config loader 
def load_config():
    global config
    default = {
        "deviation_threshold": 2.0,
        "measurement_interval_seconds": 60,
        "discovery_interval_seconds": 30,
        "peer_timeout_seconds": 180,
        "initial_peers": [],
    }
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f)
        if cfg:
            default.update(cfg.get("dt_core", {}))
    except Exception as e:
        log.warning(f"Config load failed: {e}, using defaults")
    config = default
    log.info(f"Config: threshold={config['deviation_threshold']}s, "
             f"interval={config['measurement_interval_seconds']}s")


# BaSyx data access 
def _submodel_url(base, shell_id_encoded):
    return f"{base}/aasServer/shells/{shell_id_encoded}/aas/submodels/{SM_IDSHORT}/submodel"

def fetch_own_readings():
    global _cached_readings
    url = _submodel_url(AAS_URL, SHELL_ENC)
    try:
        r = requests.get(url, timeout=5, headers=BAXYX_HEADERS)
        if r.ok:
            data = r.json()
            for e in data.get("submodelElements", []):
                k = e.get("idShort")
                v = e.get("value")
                if k == "turgor_pressure_kPa":
                    _cached_readings["turgor_pressure_kPa"] = float(v)
                elif k == "leaf_temperature":
                    _cached_readings["leaf_temperature"] = float(v)
                elif k == "last_updated":
                    _cached_readings["last_updated"] = v
            log.info(f"Own BaSyx data: turgor={_cached_readings['turgor_pressure_kPa']:.4f}, "
                     f"temp={_cached_readings['leaf_temperature']:.1f}")
    except Exception as e:
        log.debug(f"Own BaSyx fetch error: {e}")


def fetch_peer_readings(pid):
    host = basyx_host(pid)
    shell_id = f"https://edt.local/aas/{pid}"
    shell_id_encoded = urllib.parse.quote(shell_id, safe="")
    url = f"http://{host}:4001{_submodel_url('', shell_id_encoded)}"
    try:
        r = requests.get(url, timeout=5, headers=BAXYX_HEADERS)
        if r.ok:
            data = r.json()
            turgor = None
            temp = None
            for e in data.get("submodelElements", []):
                if e.get("idShort") == "turgor_pressure_kPa":
                    turgor = float(e["value"])
                elif e.get("idShort") == "leaf_temperature":
                    temp = float(e["value"])
            if turgor is not None:
                return {"dt_id": pid, "turgor_kPa": turgor, "temperature": temp}
    except Exception as e:
        log.debug(f"Peer {pid} BaSyx fetch error: {e}")
    return None


# Anomaly detection logic
def detect_anomaly(own_turgor, peer_readings, threshold=None):
    if threshold is None:
        threshold = config.get("deviation_threshold", 2.0)
    
    if len(peer_readings) < 2:
        return {
            "anomaly": False,
            "reason": f"Insufficient peers ({len(peer_readings)} < 2)",
            "peer_count": len(peer_readings),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Compute the deviation
    values = []
    for r in peer_readings:
        values.append(r["turgor_kPa"])

    total = 0.0
    for v in values:
        total += v

    mean = total / len(values)

    variance_sum = 0.0
    for v in values:
        difference = v - mean
        squared_difference = difference ** 2
        variance_sum += squared_difference

    variance = variance_sum / len(values)

    if variance > 0:
        std = math.sqrt(variance)
    else:
        std = 0.0

    deviation = own_turgor - mean

    # If std=0, any difference is an anomaly
    if std == 0:
        sigma_count = float('inf') if deviation != 0 else 0.0
        is_anomaly = deviation != 0
    else:
        sigma_count = abs(deviation) / std
        is_anomaly = sigma_count > threshold

    if is_anomaly:
        log.warning(f"ANOMALY DETECTED: own={own_turgor:.4f}, "
                    f"mean={mean:.4f}, dev={deviation:.4f}, "
                    f"sigma={sigma_count}, peers={len(peer_readings)}")

    return {
        "anomaly": is_anomaly,
        "own_turgor_kPa": own_turgor,
        "peer_mean_turgor_kPa": round(mean, 4),
        "peer_std_turgor_kPa": round(std, 4),
        "deviation_kPa": round(deviation, 4),
        "sigma_count": round(sigma_count, 2) if sigma_count != float('inf') else float('inf'),
        "threshold_sigma": threshold,
        "peer_count": len(peer_readings),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# Flask routes
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"dt_id": DT_ID, "status": "running", "peers": list(peers.keys())})

@app.route("/readings", methods=["GET"])
def get_readings():
    """Return the latest cached readings from this tree's BaSyx server."""
    return jsonify({
        "dt_id": DT_ID,
        "turgor_pressure_kPa": _cached_readings["turgor_pressure_kPa"],
        "leaf_temperature": _cached_readings["leaf_temperature"],
        "timestamp": _cached_readings["last_updated"],
    })

@app.route("/anomaly", methods=["GET"])
def get_anomaly():
    if anomaly_flags:
        return jsonify({"current_anomaly": anomaly_flags[-1]})
    return jsonify({"current_anomaly": None})

@app.route("/logs", methods=["GET"])
def get_logs():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({
        "decision_log": decision_log[-limit:],
        "anomaly_flags": anomaly_flags[-limit:],
    })

@app.route("/peers", methods=["GET"])
def list_peers():
    now = time.time()
    active = {pid: info for pid, info in peers.items()
              if now - info["last_seen"] < config["peer_timeout_seconds"]}
    return jsonify({"peers": list(active.keys()), "count": len(active)})

@app.route("/heartbeat", methods=["POST"])
def receive_heartbeat():
    data = request.get_json(force=True, silent=True)
    if data:
        pid = data.get("dt_id")
        if pid and pid != DT_ID:
            peers[pid] = {
                "host": data.get("host", dt_host(pid)),
                "port": data.get("port", DT_PORT),
                "last_seen": time.time(),
            }
    return jsonify({"status": "ok"})

@app.route("/topology", methods=["GET"])
def get_topology():
    now = time.time()
    active = {pid: info for pid, info in peers.items()
              if now - info["last_seen"] < config["peer_timeout_seconds"]}
    return jsonify({
        "dt_id": DT_ID,
        "port": DT_PORT,
        "peer_count": len(active),
        "peers": active,
    })

@app.route("/leave", methods=["POST"])
def leave_federation():
    global running
    running = False
    log.warning(f"{DT_ID} LEAVING federation")
    return jsonify({"status": "left", "dt_id": DT_ID})

@app.route("/join", methods=["POST"])
def join_federation():
    global running
    running = True
    log.info(f"{DT_ID} REJOINING federation")
    return jsonify({"status": "joined", "dt_id": DT_ID})


# POST our presence to every known peer's /heartbeat endpoint
def send_heartbeats():
    for peer_id in config.get("initial_peers", []):
        if peer_id == DT_ID:
            continue
        try:
            requests.post(
                f"http://{dt_host(peer_id)}:{DT_PORT}/heartbeat",
                json={"dt_id": DT_ID, "host": dt_host(DT_ID), "port": DT_PORT},
                timeout=2,
            )
        except requests.RequestException:
            pass

# Remove peers whose heartbeats have timed out.
def prune_peers():
    while True:
        time.sleep(config.get("peer_timeout_seconds", 180) // 2)
        now = time.time()
        stale = [pid for pid, info in peers.items()
                 if now - info["last_seen"] > config["peer_timeout_seconds"]]
        for pid in stale:
            log.info(f"Peer {pid} timed out")
            del peers[pid]


# One full round: fetch own data, fetch peer data, run anomaly check
def run_analysis_cycle():
    fetch_own_readings()
    own_turgor = _cached_readings["turgor_pressure_kPa"]

    peer_readings = []
    now = time.time()
    for pid, info in list(peers.items()):
        if now - info["last_seen"] > config["peer_timeout_seconds"]:
            continue
        pr = fetch_peer_readings(pid)
        if pr:
            peer_readings.append(pr)

    result = detect_anomaly(own_turgor, peer_readings)
    decision_log.append(result)
    if result["anomaly"]:
        anomaly_flags.append(result)

    log.info(f"Analysis: anomaly={result['anomaly']}, "
            f"sigma={result.get('sigma_count', 0):.2f}, "
            f"peers={result['peer_count']}")
    return result

# Ssend heartbeats at the configured interval
def run_discovery():
    interval = config.get("discovery_interval_seconds", 30)
    while running:
        send_heartbeats()
        time.sleep(interval)

# Fetch data and run anomaly detection
def run_analysis_loop():
    interval = config.get("measurement_interval_seconds", 60)
    time.sleep(5)
    while running:
        run_analysis_cycle()
        time.sleep(interval)

# Probe every peer's dt_logic via GET /health to populate the registry.
def run_initial_discovery_burst():
    for peer_id in config.get("initial_peers", []):
        if peer_id == DT_ID:
            continue
        try:
            r = requests.get(f"http://{dt_host(peer_id)}:{DT_PORT}/health", timeout=3)
            if r.ok:
                peers[peer_id] = {
                    "host": dt_host(peer_id),
                    "port": DT_PORT,
                    "last_seen": time.time(),
                }
                log.info(f"Initial peer discovery: {peer_id}")
        except Exception:
            pass



if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    load_config()

    # We know there are 10 peers
    initial_peers = []
    for i in range(1, 11):
        pid = f"dt_{i:02d}"
        if pid != DT_ID:
            initial_peers.append(pid)
    config["initial_peers"] = initial_peers

    threading.Thread(target=run_initial_discovery_burst, daemon=True).start()
    threading.Thread(target=run_discovery, daemon=True).start()
    threading.Thread(target=run_analysis_loop, daemon=True).start()
    threading.Thread(target=prune_peers, daemon=True).start()

    log.info("=" * 60)
    log.info(f"  {DT_ID} DT LOGIC STARTED")
    log.info(f"  BaSyx URL: {AAS_URL}")
    log.info(f"  Submodel ID: {SM_ID}")
    log.info(f"  Threshold: {config.get('deviation_threshold', 2.0)} sigma")
    log.info(f"  Analysis interval: {config.get('measurement_interval_seconds', 60)}s")
    log.info(f"  Discovery interval: {config.get('discovery_interval_seconds', 30)}s")
    log.info("=" * 60)
    app.run(host="0.0.0.0", port=DT_PORT, debug=False)
