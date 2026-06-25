# Dockerfile for the Central Manager (FastAPI + Uvicorn).
# Fetches telemetry on-demand from farm adapters via REST, runs periodic
# water-allocation algorithms, and pushes commands synchronously to
# adapters. Exposed on port 8000.
FROM python:3.11-slim
RUN pip install fastapi uvicorn[standard] pydantic requests --no-cache-dir
WORKDIR /app
CMD ["uvicorn", "central_manager.main:app", "--host", "0.0.0.0", "--port", "8000"]
