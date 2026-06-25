# Tree DT service — Flask-based business-logic container
#   - Installs Python dependencies from the shared requirements.txt
#   - Runs tree_dt/service/service.py on container start

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
CMD ["python", "tree_dt/service/service.py"]
