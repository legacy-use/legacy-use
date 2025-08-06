# Hatchet Migration Guide

This document explains the migration from the self-built queue system to Hatchet Lite for job processing.

## What Changed

### Before (Self-built Queue System)
- Jobs were managed in in-memory Python queues (`deque`)
- Queue state was not persisted across restarts
- Each tenant had its own queue and processor task
- Jobs could get stuck or lost if the server crashed
- Difficult to debug and monitor queue state
- No support for distributed workers
- Complex diagnostics endpoints needed

### After (Hatchet Lite Integration)
- Jobs are managed by Hatchet Lite with PostgreSQL persistence
- Queue state is automatically persisted across restarts  
- Uses existing PostgreSQL database (no additional database needed)
- Distributed workers can process jobs from any instance
- Built-in monitoring and debugging via Hatchet dashboard
- Fault-tolerant job processing
- Scalable worker architecture
- Simplified setup with just one additional Docker container

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │───▶│  Hatchet Lite   │───▶│ Hatchet Workers │
│                 │    │                 │    │                 │
│ - Job Creation  │    │ - Queue Mgmt    │    │ - Job Execution │
│ - Status Check  │    │ - Persistence   │    │ - Fault Tolerant│
│ - Cancellation  │    │ - Monitoring    │    │ - Scalable      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                       │                 │
                       │ Uses existing   │
                       │ PostgreSQL DB   │
                       └─────────────────┘
```

## Setup Instructions

### 1. Start Services

```bash
# Start all services including Hatchet Lite
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

# Or use the included Docker service
docker-compose up -d hatchet-worker
```

## Monitoring

### Hatchet Dashboard
- Access at: http://localhost:8080
- View workflows, jobs, and worker status
- No login required for Hatchet Lite

### API Endpoints
- Job queue status: `GET /jobs/queue/status`
- Queue resync: `POST /jobs/queue/resync` (now informational only)
- Note: Diagnostics endpoints have been removed as they are obsolete

## Key Files Changed

### New Files
- `server/utils/hatchet_client.py` - Hatchet client wrapper
- `server/utils/hatchet_job_execution.py` - New job execution interface
- `server/hatchet_worker.py` - Dedicated worker process
- `scripts/generate_hatchet_token.sh` - Token generation script

### Modified Files
- `docker-compose.yml` - Added Hatchet Lite service
- `pyproject.toml` - Added hatchet-sdk dependency
- `server/routes/jobs.py` - Updated to use Hatchet
- `server/server.py` - Updated imports

### Removed Files
- `server/utils/job_execution.py` - Legacy queue system (removed)
- `server/routes/diagnostics.py` - Obsolete diagnostics endpoints (removed)

## Migration Benefits

1. **Persistence**: Jobs survive server restarts
2. **Scalability**: Multiple workers can process jobs
3. **Reliability**: Built-in retry and error handling
4. **Monitoring**: Real-time dashboard and metrics
5. **Debugging**: Better visibility into job execution
6. **Fault Tolerance**: Jobs won't get lost or stuck

## Rollback Plan

⚠️ **Note**: Legacy files have been removed for simplicity. Rollback would require:

1. Restore files from git history
2. Revert imports in `server/routes/jobs.py` and `server/server.py`
3. Remove Hatchet Lite service from docker-compose.yml
4. Restore diagnostics endpoints if needed

## Troubleshooting

### Worker Not Starting
- Check `HATCHET_CLIENT_TOKEN` is set
- Verify Hatchet Lite is running: `docker-compose ps hatchet`
- Check network connectivity to hatchet:7070

### Jobs Not Processing
- Check worker logs: `docker-compose logs hatchet-worker`
- Verify worker is registered in Hatchet dashboard at http://localhost:8080
- Check job status in database vs Hatchet

### Token Issues
- Regenerate token with `./scripts/generate_hatchet_token.sh`
- Ensure token is properly set in environment variables

## Environment Variables

Required for Hatchet integration:

```bash
HATCHET_CLIENT_TOKEN=your-token-here
HATCHET_CLIENT_TLS_STRATEGY=none
HATCHET_CLIENT_HOST=hatchet
HATCHET_CLIENT_PORT=7070
```