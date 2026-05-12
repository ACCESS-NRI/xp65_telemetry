FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy ingester code and dependencies
COPY ingester/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingester/dump_conda_telemetry.py .
COPY ingester/upload_conda_telemetry.py .
COPY ingester/tracked_packages.txt .
COPY postgres/init.sql /schema.sql
COPY ingester/entrypoint.sh .

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
