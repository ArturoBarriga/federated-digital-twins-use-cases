# Dockerfile for the NGSI-LD adapter container (REST server)
# Runs adapter.py as an HTTP server that exposes /telemetry and /command.
# Central manager fetches sensor data on-demand via GET /telemetry and
# pushes irrigation commands synchronously via POST /command.
# The adapter reads from / writes to the FIWARE Orion-LD digital twin.
FROM python:3.11-slim
RUN pip install requests pydantic --no-cache-dir
WORKDIR /app
CMD ["python", "-u", "adapter.py"]