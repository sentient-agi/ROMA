# Docker Setup for SentientResearchAgent

## Quick Start

```bash
# Run the setup script
./setup.sh

# Or manually:
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

## Architecture

This Docker setup provides:
- **Backend**: Python with PDM (using uv backend) on port 5000
- **Frontend**: React dev server on port 5173

## Configuration

1. Copy `.env.example` to `.env`
2. Add your API keys:
   - `OPENROUTER_API_KEY`
   - `EXA_API_KEY`
   - `GOOGLE_GENAI_API_KEY`

## Commands

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Rebuild after code changes
docker compose build

# Access backend shell
docker compose exec backend bash
```

Or use the Makefile:
```bash
make up      # Start services
make logs    # View logs
make down    # Stop services
make shell   # Backend shell
```

## Development

The setup mounts source directories as volumes, so code changes are reflected immediately:
- Backend source is mounted read-only
- Frontend source is mounted read-only with hot-reload

## Troubleshooting

### Backend not starting
- Check logs: `docker compose logs backend`
- Verify API keys in `.env`
- Ensure port 5000 is not in use

### Frontend not loading
- Check logs: `docker compose logs frontend`
- Ensure backend is healthy first
- Verify port 5173 is not in use

### PDM issues
- The Dockerfile configures PDM to use the uv backend automatically
- Dependencies are installed during build

## S3 Mounting with goofys

To enable S3 mounting inside the backend container:

1. Add to your `.env` in project root:
```bash
S3_MOUNT_ENABLED=true
S3_MOUNT_DIR=/opt/sentient
S3_BUCKET_NAME=your-s3-bucket
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1

# Optional: extra goofys flags
GOOFYS_EXTRA_ARGS="--allow-other --stat-cache-ttl=10s --type-cache-ttl=10s"
```

2. Start with the S3 override automatically included by `setup.sh`, or manually:
```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.s3.yml up -d
```

Notes:
- The S3 override grants FUSE permissions (`/dev/fuse`, `SYS_ADMIN`, apparmor unconfined).
- The backend image runs `/usr/local/bin/startup.sh` which mounts the bucket using `goofys` before launching the app.
- All variables from `.env` are injected into the container via `env_file` and read by the startup script.
- macOS (Docker Desktop): FUSE mounts are not supported inside containers. `setup.sh` will mount S3 on the host at `/opt/sentient` and bind it into the container. The startup script detects this and skips in-container goofys after verifying it maps to the correct bucket. Ensure `/opt` is added under Docker Desktop → Settings → Resources → File Sharing.
