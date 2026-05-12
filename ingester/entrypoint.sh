#!/bin/bash
set -e

# Build database connection string
DBURL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Output file for flattened telemetry
NDJSON_FILE="/tmp/conda_imports_$(date +%s).ndjson"
STREAM_FILE="/tmp/conda_imports_$(date +%s).pipe"

echo "[$(date)] Starting xp65 conda telemetry ingestion..."
echo "[$(date)] Source: ${LOGS_DIR}"
echo "[$(date)] Database: ${DBURL}"

echo "[$(date)] Mode: users_only"

# Allow custom max files, default to all (0)
MAX_FILES_OPTION=""
if [ -n "$INGEST_MAX_FILES" ] && [ "$INGEST_MAX_FILES" != "0" ]; then
  MAX_FILES_OPTION="--max-files $INGEST_MAX_FILES"
fi

# Dump telemetry and upload in parallel via FIFO stream.
rm -f "$STREAM_FILE"
mkfifo "$STREAM_FILE"

echo "[$(date)] Starting upload_conda_telemetry.py (stream mode)..."
python /app/upload_conda_telemetry.py \
  --db "$DBURL" \
  --schema-file /schema.sql \
  "$STREAM_FILE" &
UPLOAD_PID=$!

echo "[$(date)] Running dump_conda_telemetry.py..."
python /app/dump_conda_telemetry.py \
  --source-dir "$LOGS_DIR" \
  --output-file "$STREAM_FILE" \
  --allow-missing-source \
  $MAX_FILES_OPTION

wait "$UPLOAD_PID"

echo "[$(date)] Ingestion complete."

# Cleanup
rm -f "$NDJSON_FILE" "$STREAM_FILE"

echo "[$(date)] Keeping container running for Grafana access..."
# Keep container alive for manual debugging/queries if needed
exec sleep infinity
