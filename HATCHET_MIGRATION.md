# Hatchet Migration Guide

This document explains the migration from the self-built queue system to Hatchet for job processing.

## What Changed

### Before (Self-built Queue System)
- Jobs were managed in in-memory Python queues (`deque`)
- Queue state was not persisted across restarts
- Each tenant had its own queue and processor task
- Jobs could get stuck or lost if the server crashed
- Difficult to debug and monitor queue state
- No support for distributed workers

### After (Hatchet Integration)
- Jobs are managed by Hatchet server with PostgreSQL persistence
- Queue state is automatically persisted across restarts
- Distributed workers can process jobs from any instance
- Built-in monitoring and debugging via Hatchet dashboard
- Fault-tolerant job processing
- Scalable worker architecture

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │───▶│  Hatchet Server │───▶│ Hatchet Workers │
│                 │    │                 │    │                 │
│ - Job Creation  │    │ - Queue Mgmt    │    │ - Job Execution │
│ - Status Check  │    │ - Persistence   │    │ - Fault Tolerant│
│ - Cancellation  │    │ - Monitoring    │    │ - Scalable      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Setup Instructions

### 1. Start Services

```bash
# Start all services including Hatchet
docker-compose up -d
```

### 2. Generate Hatchet Token

```bash
# Generate the client token
./scripts/generate_hatchet_token.sh

# Add the token to your .env file
echo "HATCHET_CLIENT_TOKEN=<your-token>" >> .env
```

### 3. Start Hatchet Worker

The Hatchet worker needs to run as a separate process:

```bash
# In production, run this as a service
python server/hatchet_worker.py

# Or in Docker (add to docker-compose if needed)
docker run -it --rm \
  --network legacy-use_default \
  -e HATCHET_CLIENT_TOKEN=$HATCHET_CLIENT_TOKEN \
  -e DATABASE_URL=$DATABASE_URL \
  -e HATCHET_CLIENT_TLS_STRATEGY=none \
  -e HATCHET_CLIENT_HOST=hatchet-engine \
  -e HATCHET_CLIENT_PORT=7070 \
  your-app-image python server/hatchet_worker.py
```

## Monitoring

### Hatchet Dashboard
- Access at: http://localhost:8081
- Login: admin@example.com / Admin123!!
- View workflows, jobs, and worker status

### API Endpoints
- Job queue status: `GET /jobs/queue/status`
- Diagnostics: `GET /diagnostics`
- Queue resync: `POST /jobs/queue/resync` (now informational only)

## Key Files Changed

### New Files
- `server/utils/hatchet_client.py` - Hatchet client wrapper
- `server/utils/hatchet_job_execution.py` - New job execution interface
- `server/hatchet_worker.py` - Dedicated worker process
- `scripts/generate_hatchet_token.sh` - Token generation script
- `Hatchetfile` - Caddy configuration for Hatchet UI

### Modified Files
- `docker-compose.yml` - Added Hatchet services
- `pyproject.toml` - Added hatchet-sdk dependency
- `server/routes/jobs.py` - Updated to use Hatchet
- `server/routes/diagnostics.py` - Updated diagnostics
- `server/server.py` - Updated imports

### Deprecated Files
- `server/utils/job_execution.py` - Still exists but most functions deprecated

## Migration Benefits

1. **Persistence**: Jobs survive server restarts
2. **Scalability**: Multiple workers can process jobs
3. **Reliability**: Built-in retry and error handling
4. **Monitoring**: Real-time dashboard and metrics
5. **Debugging**: Better visibility into job execution
6. **Fault Tolerance**: Jobs won't get lost or stuck

## Rollback Plan

If needed, you can rollback by:

1. Stop Hatchet services
2. Revert imports in `server/routes/jobs.py` and `server/server.py`
3. Use original `server/utils/job_execution.py`
4. Remove Hatchet services from docker-compose.yml

## Troubleshooting

### Worker Not Starting
- Check `HATCHET_CLIENT_TOKEN` is set
- Verify Hatchet services are running
- Check network connectivity to hatchet-engine:7070

### Jobs Not Processing
- Check worker logs
- Verify worker is registered in Hatchet dashboard
- Check job status in database vs Hatchet

### Token Issues
- Regenerate token with `./scripts/generate_hatchet_token.sh`
- Ensure token is properly set in environment variables

## Environment Variables

Required for Hatchet integration:

```bash
HATCHET_CLIENT_TOKEN=your-token-here
HATCHET_CLIENT_TLS_STRATEGY=none
HATCHET_CLIENT_HOST=hatchet-engine
HATCHET_CLIENT_PORT=7070
```