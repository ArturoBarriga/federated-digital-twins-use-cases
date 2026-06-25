# Dockerfile for the farm simulator container
# Runs farm_simulator.py which extends the abstract FarmSimulator from
# farm_base/ and pushes telemetry into the Eclipse Ditto digital twin.
FROM python:3.11-slim
RUN pip install requests --no-cache-dir
WORKDIR /app
CMD ["python", "-u", "farm_simulator.py"]
