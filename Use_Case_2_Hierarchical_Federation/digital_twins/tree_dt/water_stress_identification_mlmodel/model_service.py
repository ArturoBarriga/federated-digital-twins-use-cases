
# Loads a persisted scikit-learn Random Forest model (rf-model.pkl) trained on
# physiological plant data.  Expects a single-row 6-feature input array (already
# min-max normalised by the preprocessor service) and returns a stress label:
#  0 → No stress,  1 → Mid stress,  2 → Severe stress


from flask import Flask, request, jsonify
import joblib
import os
from datetime import datetime, timezone

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['CUDA_VISIBLE_DEVICES'] = "0"

app = Flask(__name__)

def _ts():
    return datetime.now(timezone.utc).isoformat()

# Load the trained Random Forest classifier (persisted with joblib)
MODEL = joblib.load('data/rf-model.pkl')
print(f"[ML Model][{_ts()}] Model loaded successfully from data/rf-model.pkl", flush=True)

# Human-readable labels matching the model's output classes
MODEL_LABELS = ['No stress (0)', 'Mid stress (1)', 'Severe stress (2)']
print(f"[ML Model][{_ts()}] Labels: {MODEL_LABELS}", flush=True)


@app.route('/predict', methods=['POST'])
def predict():
    t0 = datetime.now(timezone.utc)
    req_json = request.get_json()
    modelInput = req_json['modelInput']

    print(f"[ML Model][{_ts()}] Received from TreeService: {modelInput}", flush=True)

    seq_predictions = MODEL.predict([modelInput])
    label = MODEL_LABELS[int(seq_predictions[0])]

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[ML Model][{_ts()}] Prediction: class={int(seq_predictions[0])} label=\"{label}\" (took {elapsed*1000:.1f}ms)", flush=True)
    return jsonify(status='HTTP 200 OK status code', output=label)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    print(f"[ML Model][{_ts()}] Starting on port 8000", flush=True)
    app.run(host='0.0.0.0', port=8000, debug=False)
