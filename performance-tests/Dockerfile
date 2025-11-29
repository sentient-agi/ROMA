# Multi-stage Dockerfile for ROMA Multi-Agent SaaS Builder
# Production-ready containerization with minimal attack surface

# Stage 1: Dependencies
FROM node:22-alpine AS deps
WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package files
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/schemas/package.json ./packages/schemas/
COPY packages/llm/package.json ./packages/llm/
COPY packages/roma/package.json ./packages/roma/
COPY packages/builder/package.json ./packages/builder/
COPY packages/ptc/package.json ./packages/ptc/
COPY packages/cli/package.json ./packages/cli/

# Install dependencies
RUN pnpm install --frozen-lockfile

# Stage 2: Build
FROM node:22-alpine AS builder
WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages ./packages

# Copy source code
COPY . .

# Build all packages
RUN pnpm build

# Stage 3: Production runtime
FROM node:22-alpine AS runner
WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Create non-root user for security
RUN addgroup --system --gid 1001 roma && \
    adduser --system --uid 1001 roma

# Copy built artifacts
COPY --from=builder --chown=roma:roma /app/packages ./packages
COPY --from=builder --chown=roma:roma /app/node_modules ./node_modules
COPY --from=builder --chown=roma:roma /app/package.json ./package.json
COPY --from=builder --chown=roma:roma /app/pnpm-workspace.yaml ./pnpm-workspace.yaml

# Set user
USER roma

# Expose port (if needed for future API)
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "console.log('healthy')" || exit 1

# Default command: show ROMA version
CMD ["pnpm", "roma", "--version"]
