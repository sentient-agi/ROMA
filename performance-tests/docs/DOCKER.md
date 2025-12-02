# Docker Guide for ROMA

This guide covers containerization for the ROMA Multi-Agent SaaS Builder.

## Quick Start

### Build the Docker image

```bash
docker build -t roma-builder:latest .
```

### Run ROMA in a container

```bash
# Check version
docker run --rm roma-builder:latest pnpm roma --version

# Run with the OnThisDay example
docker run --rm \
  -v $(pwd)/examples:/app/examples:ro \
  -v $(pwd)/out:/app/out \
  roma-builder:latest \
  pnpm roma:onthisday
```

### Using Docker Compose

```bash
# Build and run production service
docker compose up roma

# Run development service with shell access
docker compose run --rm roma-dev

# Run OnThisDay demo
docker compose run --rm roma pnpm roma:onthisday

# Clean up
docker compose down -v
```

## Multi-Stage Build

The Dockerfile uses a **3-stage build** for optimal security and size:

### Stage 1: Dependencies (`deps`)
- Base: `node:22-alpine`
- Installs pnpm and project dependencies
- Uses `--frozen-lockfile` for reproducible builds

### Stage 2: Build (`builder`)
- Copies dependencies from `deps` stage
- Builds all TypeScript packages
- **339MB** uncompressed

### Stage 3: Production (`runner`)
- Minimal runtime image
- Runs as non-root user (`roma:roma`, UID/GID 1001)
- Only includes built artifacts and production dependencies
- Includes health check
- **~200MB** compressed

## Development Workflow

### 1. Local Development (Hot Reload)

```bash
# Start dev container with shell
docker compose run --rm roma-dev /bin/sh

# Inside container
pnpm build
pnpm roma:onthisday
```

### 2. Testing in Container

```bash
# Run tests
docker compose run --rm roma-dev pnpm test

# Run specific test suite
docker compose run --rm roma-dev pnpm --filter @roma/builder test
```

### 3. Building Locally, Running in Container

```bash
# Build locally
pnpm build

# Run in container (mounts local build)
docker compose run --rm \
  -v $(pwd)/packages:/app/packages:ro \
  roma pnpm roma:onthisday
```

## Volume Mounts

### Production Service (`roma`)

- `/app/packages` - Source code (read-only)
- `/app/examples` - Example intake files (read-only)
- `/app/out` - Generated artifacts (read-write)
- `/app/.roma` - Execution state (persistent volume)

### Development Service (`roma-dev`)

- `/app/packages` - Source code (read-write for hot reload)
- `/app/node_modules` - Named volume for dependencies
- `/app/examples` - Example files (read-write)
- `/app/out` - Generated artifacts (read-write)

## Environment Variables

Set these in `.env` file or pass via `-e`:

```env
# Node environment
NODE_ENV=production

# Logging
LOG_LEVEL=info

# OpenTelemetry (optional)
HONEYCOMB_API_KEY=your_api_key_here
OTEL_SERVICE_NAME=roma-builder

# Builder-specific (if needed)
BUILDER_MAX_FEATURES=100
BUILDER_TIMEOUT=300000
```

## Resource Limits

Default limits in `docker-compose.yml`:

- **CPU**: 2.0 cores max, 0.5 cores reserved
- **Memory**: 2GB max, 512MB reserved

Adjust based on your workload:

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'      # For large projects
      memory: 4G
```

## Security Best Practices

### 1. Non-Root User
The container runs as user `roma` (UID 1001) for enhanced security.

### 2. Read-Only Mounts
Source code is mounted read-only in production to prevent accidental modification.

### 3. Health Checks
Built-in health check ensures the container is responsive:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "console.log('healthy')" || exit 1
```

### 4. Minimal Base Image
Uses Alpine Linux for smaller attack surface (~200MB vs 1GB+ for full Node images).

### 5. No Secrets in Image
All secrets are passed via environment variables, never baked into the image.

## Troubleshooting

### Container Fails to Start

```bash
# Check logs
docker compose logs roma

# Run with interactive shell
docker compose run --rm roma /bin/sh
```

### Permission Issues

```bash
# Ensure output directory has correct permissions
chmod 755 out
chown -R $(id -u):$(id -g) out
```

### Build Failures

```bash
# Clean build with no cache
docker build --no-cache -t roma-builder:latest .

# Check specific stage
docker build --target deps -t roma-deps .
docker run --rm -it roma-deps /bin/sh
```

### Out of Memory

```bash
# Increase Docker memory limit (Docker Desktop)
# Settings → Resources → Memory: 4GB+

# Or adjust container limits in docker-compose.yml
```

## Production Deployment

### 1. Build Optimized Image

```bash
# Build with build args for optimization
docker build \
  --build-arg NODE_ENV=production \
  --build-arg PNPM_FLAGS="--prod --frozen-lockfile" \
  -t roma-builder:1.0.0 \
  .
```

### 2. Push to Registry

```bash
# Tag for registry
docker tag roma-builder:1.0.0 your-registry.com/roma-builder:1.0.0

# Push
docker push your-registry.com/roma-builder:1.0.0
```

### 3. Run in Production

```bash
docker run -d \
  --name roma-builder-prod \
  --restart unless-stopped \
  --memory 2g \
  --cpus 2.0 \
  -v /var/roma/out:/app/out \
  -v /var/roma/state:/app/.roma \
  -e NODE_ENV=production \
  -e HONEYCOMB_API_KEY=${HONEYCOMB_API_KEY} \
  your-registry.com/roma-builder:1.0.0 \
  pnpm roma build --production
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Build Docker image
  run: docker build -t roma-builder:${{ github.sha }} .

- name: Run smoke test
  run: |
    docker run --rm roma-builder:${{ github.sha }} pnpm roma --version
    docker run --rm roma-builder:${{ github.sha }} pnpm test

- name: Push to registry
  if: github.ref == 'refs/heads/main'
  run: |
    docker tag roma-builder:${{ github.sha }} $REGISTRY/roma-builder:latest
    docker push $REGISTRY/roma-builder:latest
```

## Performance Tips

### 1. Layer Caching
- Dependencies change rarely → Cached in Stage 1
- Source code changes often → Built in Stage 2
- Rebuild time: ~30s (with cache) vs 3min (no cache)

### 2. BuildKit
Enable Docker BuildKit for faster builds:

```bash
export DOCKER_BUILDKIT=1
docker build -t roma-builder:latest .
```

### 3. Multi-Platform Builds

```bash
# Build for both amd64 and arm64
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t roma-builder:multiarch \
  --push \
  .
```

## Maintenance

### Clean Up Old Images

```bash
# Remove unused images
docker image prune -a -f

# Remove stopped containers
docker container prune -f

# Remove unused volumes
docker volume prune -f
```

### Update Base Image

```bash
# Pull latest Node 22 Alpine
docker pull node:22-alpine

# Rebuild
docker build --pull -t roma-builder:latest .
```

## Support

For issues with containerization:
1. Check logs: `docker compose logs roma`
2. Verify Docker version: `docker version` (requires 20.10+)
3. Verify Compose version: `docker compose version` (requires 2.0+)
4. Report issues: https://github.com/anthropics/roma/issues
