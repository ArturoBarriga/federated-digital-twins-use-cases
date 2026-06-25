# Dockerfile for the NGSI-LD farm simulator container
FROM python:3.11-slim
RUN pip install requests --no-cache-dir
WORKDIR /app
CMD ["python", "-u", "farm_simulator.py"]