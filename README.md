# XP65 Conda Telemetry System

A standalone Docker-based analytics system for ingesting and visualizing conda environment usage telemetry from NCI GADI xp65 logs.

## Quick Start

1. **Clone/navigate to this directory:**
   ```bash
   cd /home/romain/PROJECTS/xp65-telemetry
   ```

2. **(Optional) Update the logs source path in `.env`:**
   ```bash
   # Edit .env and update LOGS_SOURCE to your actual path
   # Default is /home/romain/NCI_gadi/xp65_logs
   ```

3. **Start the system:**
   ```bash
   docker-compose up
   ```

   This will:
   - Start PostgreSQL database
   - Run the ingester (dump + upload)
   - Start Grafana
   - Provision datasource and dashboard automatically

   If you set `DATABASE_URL`, the ingester will send data to that managed PostgreSQL instance instead of using the local Compose database.

4. **Access Grafana:**
   - Open http://localhost:3000
   - Login: `admin` / `admin`
   - Dashboard "XP65 Conda Telemetry" will be ready to use

## What's Included

- **PostgreSQL 16**: Database for telemetry storage
- **Grafana 11.1.0**: Visualization and dashboarding
- **Python Ingester**: Automatically dumps and uploads telemetry on startup
  - Idempotent via event_hash unique key
  - Supports partial ingestion with `INGEST_MAX_FILES`
  - Graceful handling of missing source directory

## Configuration

Edit `.env` to customize:

```env
# Optional: managed PostgreSQL connection string for the ingester
DATABASE_URL=postgresql://USER:PASSWORD@managed-db.example.com:5432/RESOURCES

# Database credentials (used when DATABASE_URL is not set)
DB_PASSWORD=postgres
DB_USER=postgres
DB_NAME=RESOURCES

# Grafana login
GRAFANA_PASSWORD=admin

# Source log directory (critical: update to your path)
LOGS_SOURCE=/home/romain/NCI_gadi/xp65_logs

# Optional: limit files per ingest run (0 = all)
INGEST_MAX_FILES=0
```

### Managed database notes

- Set `DATABASE_URL` in `.env` if you want the ingester to target a managed PostgreSQL instance.
- This is intentionally a minimal ingestion-side change; Grafana provisioning still points at the local Compose PostgreSQL service.

### Configure tracked packages

The ingester can restrict tracking to a configurable package allowlist file:

- Edit [ingester/tracked_packages.txt](ingester/tracked_packages.txt) using your environment-style package lines.
- During ingestion, only normalized package names from this file are inserted into `conda_env_packages`.
- To clean old rows that are not in the allowlist, run ingestion with cleanup once:

```bash
docker compose run --rm --entrypoint bash ingester -lc 'DBURL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"; python /app/upload_conda_telemetry.py --db "$DBURL" --schema-file /schema.sql --tracked-packages-file /app/tracked_packages.txt --cleanup-existing-packages /dev/null'
```

## Database Schema

Tables:
- `conda_env_sessions`: telemetry events (user sessions, packages, timestamps, etc.)
- `conda_env_packages`: package imports per session
- `conda_env_ingest_runs`: audit log of ingestion runs

Views (pre-aggregated for fast dashboards):
- `conda_env_daily_usage`: daily active users and session counts by environment
- `conda_env_package_daily_usage`: daily package usage and user counts

## Usage Scenarios

### Initial Load
```bash
docker-compose up
# Ingester will process entire logs directory and upload
```

### Re-ingest (idempotent)
```bash
docker-compose restart ingester
# Duplicate events are skipped automatically
```

### Limit to subset of files
```bash
# Edit .env: INGEST_MAX_FILES=50
docker-compose up
```

### Manual queries
```bash
docker exec xp65-postgres psql -U postgres -d RESOURCES -c \
  "SELECT env_name, count(*) FROM conda_env_sessions GROUP BY env_name;"
```

### Grafana API
Grafana is provisioned with:
- PostgreSQL datasource at `postgres:5432`
- Dashboard "XP65 Conda Telemetry" with 4 panels:
  1. Active Users by Environment (time series)
  2. Sessions by Environment (time series)
  3. Top Users (table)
  4. Unique Users by Environment (bar chart)

## Troubleshooting

**Connection refused**
- Ensure `LOGS_SOURCE` in `.env` points to a valid directory
- Check `docker-compose logs ingester` for details

**No data visible in Grafana**
- Verify PostgreSQL is healthy: `docker-compose logs postgres`
- Check ingester logs: `docker-compose logs ingester`
- Manually query: `docker exec xp65-postgres psql -U postgres -d RESOURCES -c "SELECT count(*) FROM conda_env_sessions;"`

**Want to restart everything**
```bash
docker-compose down -v  # Remove volumes
docker-compose up --build
```

## Architecture

```
xp65-telemetry/
├── docker-compose.yml          # Service orchestration
├── .env                        # Configuration (edit LOGS_SOURCE here)
├── Dockerfile                  # Ingester image
├── ingester/
│   ├── dump_conda_telemetry.py   # Flatten imports.jsonl to NDJSON
│   ├── upload_conda_telemetry.py # Insert into Postgres
│   ├── entrypoint.sh            # Orchestrates dump + upload
│   └── requirements.txt         # Python deps (psycopg2-binary)
├── postgres/
│   └── init.sql               # Schema, tables, indexes, views
└── grafana/
    └── provisioning/
        ├── datasources/postgres.yaml
        └── dashboards/conda-telemetry.json
```

## Performance Notes

- **309K events** from 215 user files ingests in ~30 seconds
- Idempotent hashing ensures safe re-ingestion
- Daily summary views are materialized for fast panel rendering
- Indexes on (env_name, time), (user_id, time), (package_name)

## Next Steps

- Monitor ingestion logs for patterns or errors
- Adjust Grafana dashboard panels for specific use cases
- Plan retention/archival policy if telemetry grows
- Consider scheduling periodic re-ingestion (cron outside container)
