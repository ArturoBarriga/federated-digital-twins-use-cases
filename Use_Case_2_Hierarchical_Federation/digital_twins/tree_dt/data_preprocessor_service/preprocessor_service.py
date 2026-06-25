
# Receives raw sensor values from the Tree DT service, applies min-max
# normalisation using pre-defined physiological bounds, and returns a
# single-row array ready for the ML model.

from flask import Flask, request, jsonify
from datetime import datetime, timezone

app = Flask(__name__)

# Feature order expected by the ML model (must match training order)
FEATURE_NAMES = [
    "leaf_turgor_pressure_kPa",
    "leaf_temperature",
    "canopy_humidity",
    "stomatal_conductance",
    "sap_flow_rate",
    "trunk_size",
]

MIN_MAX = {
    "leaf_turgor_pressure_kPa": (0.0, 2.5),    # kPa,  0.0 – 2.5
    "leaf_temperature":        (10.0, 45.0),   # °C,  10 – 45
    "canopy_humidity":         (30.0, 100.0),  # %,   30 – 100
    "stomatal_conductance":    (0.0, 1.0),     # relative conductance 0–1
    "sap_flow_rate":           (0.0, 50.0),    # kg/h,  0 – 50
    "trunk_size":              (130.0, 160.0), # mm,  130 – 160
}

def _ts():
    return datetime.now(timezone.utc).isoformat()


@app.route("/preprocess", methods=["POST"])
def preprocess():
    t0 = datetime.now(timezone.utc)
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Empty request body"}), 400

    print(f"[Preprocessor][{_ts()}] Received from TreeService: {body}", flush=True)

    raw = []
    details = []
    for name in FEATURE_NAMES:
        val = body.get(name)
        if val is None:
            return jsonify({"error": f"Missing feature: {name}"}), 400
        try:
            fval = float(val)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid value for {name}: {val}"}), 400
        _min, _max = MIN_MAX[name]
        normalized = (fval - _min) / (_max - _min) if _max != _min else 0.0
        raw.append(round(normalized, 6))
        details.append(f"{name}: {fval} → {raw[-1]:.6f}  (range [{_min},{_max}])")

    for line in details:
        print(f"[Preprocessor][{_ts()}]   {line}", flush=True)

    result = {"modelInput": raw}
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[Preprocessor][{_ts()}] Returning to TreeService: {result}  (took {elapsed*1000:.1f}ms)", flush=True)
    return jsonify(result)


if __name__ == "__main__":
    print(f"[Preprocessor][{_ts()}] Starting on port 8000", flush=True)
    app.run(host="0.0.0.0", port=8000, debug=False)
