"""Docker MCP Server for ROMA.

Provides code generation tools for Docker configurations including:
- Dockerfile generation
- docker-compose.yml generation
- Multi-stage builds
- Development vs production configurations
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from roma_dspy.tools.mcp.servers.base import BaseMCPServer, GenerationResult, TemplateResult


class DockerConfig(BaseModel):
    """Configuration for Docker generation."""

    app_name: str = Field(..., description="Application name")
    language: str = Field("node", description="Programming language (node, python, go, rust)")
    port: int = Field(3000, description="Application port")
    multi_stage: bool = Field(True, description="Use multi-stage build")


class DockerMCPServer(BaseMCPServer):
    """MCP Server for Docker code generation.

    Provides tools for generating Dockerfiles, docker-compose configurations,
    and related Docker artifacts following best practices.
    """

    name = "roma-docker-mcp"
    description = "Docker code generation tools for ROMA"
    version = "1.0.0"

    def _register_tools(self) -> None:
        """Register Docker generation tools."""
        self._register_tool("generate_dockerfile", self.generate_dockerfile)
        self._register_tool("generate_compose", self.generate_compose)
        self._register_tool("generate_dockerignore", self.generate_dockerignore)
        self._register_tool("generate_dev_dockerfile", self.generate_dev_dockerfile)
        self._register_tool("generate_full_stack", self.generate_full_stack)

    def generate_dockerfile(
        self,
        language: str = "node",
        app_name: str = "app",
        port: int = 3000,
        multi_stage: bool = True,
        node_version: str = "20",
        python_version: str = "3.12",
        with_healthcheck: bool = True,
        with_non_root_user: bool = True,
    ) -> TemplateResult:
        """Generate a production-ready Dockerfile.

        Args:
            language: Programming language (node, python, go, rust)
            app_name: Application name
            port: Application port
            multi_stage: Use multi-stage build for smaller images
            node_version: Node.js version (for node apps)
            python_version: Python version (for python apps)
            with_healthcheck: Include HEALTHCHECK instruction
            with_non_root_user: Run as non-root user

        Returns:
            Generated Dockerfile
        """
        if language == "node":
            return self._generate_node_dockerfile(
                app_name, port, multi_stage, node_version, with_healthcheck, with_non_root_user
            )
        elif language == "python":
            return self._generate_python_dockerfile(
                app_name, port, multi_stage, python_version, with_healthcheck, with_non_root_user
            )
        elif language == "go":
            return self._generate_go_dockerfile(
                app_name, port, multi_stage, with_healthcheck, with_non_root_user
            )
        else:
            return self._generate_node_dockerfile(
                app_name, port, multi_stage, node_version, with_healthcheck, with_non_root_user
            )

    def _generate_node_dockerfile(
        self,
        app_name: str,
        port: int,
        multi_stage: bool,
        node_version: str,
        with_healthcheck: bool,
        with_non_root_user: bool,
    ) -> TemplateResult:
        """Generate Node.js Dockerfile."""
        healthcheck = ""
        if with_healthcheck:
            healthcheck = f'''
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
  CMD wget --no-verbose --tries=1 --spider http://localhost:{port}/health || exit 1
'''

        user_setup = ""
        user_switch = ""
        if with_non_root_user:
            user_setup = """
# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 nodejs
"""
            user_switch = """
USER nodejs
"""

        if multi_stage:
            content = f'''# syntax=docker/dockerfile:1

# ============================================
# Build stage
# ============================================
FROM node:{node_version}-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# Copy source and build
COPY . .
RUN npm run build

# ============================================
# Production stage
# ============================================
FROM node:{node_version}-alpine AS production

WORKDIR /app

# Set environment
ENV NODE_ENV=production
ENV PORT={port}
{user_setup}
# Copy built application
COPY --from=builder --chown=nodejs:nodejs /app/dist ./dist
COPY --from=builder --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/package*.json ./
{user_switch}
EXPOSE {port}
{healthcheck}
CMD ["node", "dist/main.js"]
'''
        else:
            content = f'''# syntax=docker/dockerfile:1

FROM node:{node_version}-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV PORT={port}
{user_setup}
# Install dependencies
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# Copy application
COPY --chown=nodejs:nodejs . .

RUN npm run build
{user_switch}
EXPOSE {port}
{healthcheck}
CMD ["node", "dist/main.js"]
'''

        return TemplateResult(
            filename="Dockerfile",
            content=content,
            language="dockerfile",
            path="",
            dependencies=[],
        )

    def _generate_python_dockerfile(
        self,
        app_name: str,
        port: int,
        multi_stage: bool,
        python_version: str,
        with_healthcheck: bool,
        with_non_root_user: bool,
    ) -> TemplateResult:
        """Generate Python Dockerfile."""
        healthcheck = ""
        if with_healthcheck:
            healthcheck = f'''
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1
'''

        user_setup = ""
        user_switch = ""
        if with_non_root_user:
            user_setup = """
# Create non-root user
RUN groupadd --system --gid 1001 appgroup && \\
    useradd --system --uid 1001 --gid appgroup appuser
"""
            user_switch = """
USER appuser
"""

        if multi_stage:
            content = f'''# syntax=docker/dockerfile:1

# ============================================
# Build stage
# ============================================
FROM python:{python_version}-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ============================================
# Production stage
# ============================================
FROM python:{python_version}-slim AS production

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT={port}
{user_setup}
# Copy wheels and install
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /wheels/*

# Copy application
COPY --chown=appuser:appgroup . .
{user_switch}
EXPOSE {port}
{healthcheck}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
'''
        else:
            content = f'''# syntax=docker/dockerfile:1

FROM python:{python_version}-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT={port}
{user_setup}
# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=appuser:appgroup . .
{user_switch}
EXPOSE {port}
{healthcheck}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
'''

        return TemplateResult(
            filename="Dockerfile",
            content=content,
            language="dockerfile",
            path="",
            dependencies=[],
        )

    def _generate_go_dockerfile(
        self,
        app_name: str,
        port: int,
        multi_stage: bool,
        with_healthcheck: bool,
        with_non_root_user: bool,
    ) -> TemplateResult:
        """Generate Go Dockerfile."""
        healthcheck = ""
        if with_healthcheck:
            healthcheck = f'''
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
  CMD wget --no-verbose --tries=1 --spider http://localhost:{port}/health || exit 1
'''

        user_switch = ""
        if with_non_root_user:
            user_switch = """
USER 1001:1001
"""

        content = f'''# syntax=docker/dockerfile:1

# ============================================
# Build stage
# ============================================
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Install certificates for HTTPS
RUN apk add --no-cache ca-certificates

# Download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Build application
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /app/{app_name} .

# ============================================
# Production stage
# ============================================
FROM scratch AS production

WORKDIR /app

ENV PORT={port}

# Copy certificates and binary
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /app/{app_name} .
{user_switch}
EXPOSE {port}
{healthcheck}
ENTRYPOINT ["/{app_name}"]
'''

        return TemplateResult(
            filename="Dockerfile",
            content=content,
            language="dockerfile",
            path="",
            dependencies=[],
        )

    def generate_compose(
        self,
        app_name: str = "app",
        services: Optional[List[str]] = None,
        with_postgres: bool = False,
        with_redis: bool = False,
        with_mongodb: bool = False,
        with_nginx: bool = False,
        app_port: int = 3000,
        environment: str = "development",
    ) -> TemplateResult:
        """Generate docker-compose.yml file.

        Args:
            app_name: Application name
            services: List of custom services to include
            with_postgres: Include PostgreSQL service
            with_redis: Include Redis service
            with_mongodb: Include MongoDB service
            with_nginx: Include Nginx reverse proxy
            app_port: Application port
            environment: Environment (development, production)

        Returns:
            Generated docker-compose.yml
        """
        service_definitions = []
        volumes = []
        networks = ["app-network"]

        # Application service
        app_depends = []
        app_env = [
            f"NODE_ENV={environment}",
            f"PORT={app_port}",
        ]

        if with_postgres:
            app_depends.append("postgres")
            app_env.append("DATABASE_URL=postgresql://postgres:postgres@postgres:5432/app")

        if with_redis:
            app_depends.append("redis")
            app_env.append("REDIS_URL=redis://redis:6379")

        if with_mongodb:
            app_depends.append("mongodb")
            app_env.append("MONGODB_URI=mongodb://mongodb:27017/app")

        depends_on = ""
        if app_depends:
            depends_on = f"""
    depends_on:
      {chr(10).join(f'      - {dep}' for dep in app_depends)}"""

        app_service = f'''  {app_name}:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {app_name}
    ports:
      - "{app_port}:{app_port}"
    environment:
{chr(10).join(f'      - {env}' for env in app_env)}{depends_on}
    networks:
      - app-network
    restart: unless-stopped'''

        service_definitions.append(app_service)

        # PostgreSQL service
        if with_postgres:
            postgres_service = '''  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - app-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped'''
            service_definitions.append(postgres_service)
            volumes.append("postgres_data:")

        # Redis service
        if with_redis:
            redis_service = '''  redis:
    image: redis:7-alpine
    container_name: redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped'''
            service_definitions.append(redis_service)
            volumes.append("redis_data:")

        # MongoDB service
        if with_mongodb:
            mongodb_service = '''  mongodb:
    image: mongo:7
    container_name: mongodb
    environment:
      - MONGO_INITDB_DATABASE=app
    volumes:
      - mongodb_data:/data/db
    ports:
      - "27017:27017"
    networks:
      - app-network
    healthcheck:
      test: echo 'db.runCommand("ping").ok' | mongosh localhost:27017/test --quiet
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped'''
            service_definitions.append(mongodb_service)
            volumes.append("mongodb_data:")

        # Nginx reverse proxy
        if with_nginx:
            nginx_service = f'''  nginx:
    image: nginx:alpine
    container_name: nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - {app_name}
    networks:
      - app-network
    restart: unless-stopped'''
            service_definitions.append(nginx_service)

        # Build volumes section
        volumes_section = ""
        if volumes:
            volumes_section = f'''
volumes:
  {chr(10).join(f'  {v}' for v in volumes)}'''

        content = f'''version: '3.8'

services:
{chr(10).join(service_definitions)}

networks:
  app-network:
    driver: bridge
{volumes_section}
'''

        return TemplateResult(
            filename="docker-compose.yml",
            content=content,
            language="yaml",
            path="",
            dependencies=[],
        )

    def generate_dockerignore(
        self,
        language: str = "node",
        additional_ignores: Optional[List[str]] = None,
    ) -> TemplateResult:
        """Generate .dockerignore file.

        Args:
            language: Programming language
            additional_ignores: Additional patterns to ignore

        Returns:
            Generated .dockerignore
        """
        common_ignores = [
            "# Git",
            ".git",
            ".gitignore",
            "",
            "# Docker",
            "Dockerfile*",
            "docker-compose*.yml",
            ".docker",
            "",
            "# IDE",
            ".idea",
            ".vscode",
            "*.swp",
            "*.swo",
            "",
            "# Environment",
            ".env*",
            "!.env.example",
            "",
            "# Documentation",
            "README.md",
            "docs",
            "*.md",
            "",
            "# CI/CD",
            ".github",
            ".gitlab-ci.yml",
            "Jenkinsfile",
        ]

        language_ignores = {
            "node": [
                "",
                "# Node.js",
                "node_modules",
                "npm-debug.log*",
                "yarn-debug.log*",
                "yarn-error.log*",
                ".npm",
                ".yarn",
                "coverage",
                ".nyc_output",
                "dist",
                "build",
            ],
            "python": [
                "",
                "# Python",
                "__pycache__",
                "*.py[cod]",
                "*$py.class",
                ".Python",
                "venv",
                ".venv",
                "env",
                ".pytest_cache",
                ".mypy_cache",
                "*.egg-info",
                "dist",
                "build",
            ],
            "go": [
                "",
                "# Go",
                "*.exe",
                "*.exe~",
                "*.dll",
                "*.so",
                "*.dylib",
                "*.test",
                "*.out",
                "vendor",
            ],
        }

        ignores = common_ignores + language_ignores.get(language, [])

        if additional_ignores:
            ignores.extend(["", "# Custom"])
            ignores.extend(additional_ignores)

        content = "\n".join(ignores) + "\n"

        return TemplateResult(
            filename=".dockerignore",
            content=content,
            language="text",
            path="",
            dependencies=[],
        )

    def generate_dev_dockerfile(
        self,
        language: str = "node",
        port: int = 3000,
        node_version: str = "20",
        python_version: str = "3.12",
    ) -> TemplateResult:
        """Generate a development Dockerfile with hot reload.

        Args:
            language: Programming language
            port: Application port
            node_version: Node.js version
            python_version: Python version

        Returns:
            Generated development Dockerfile
        """
        if language == "node":
            content = f'''# Development Dockerfile with hot reload
FROM node:{node_version}-alpine

WORKDIR /app

# Install dependencies for file watching
RUN apk add --no-cache git

# Set development environment
ENV NODE_ENV=development
ENV PORT={port}

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source (will be overridden by volume mount in dev)
COPY . .

EXPOSE {port}

# Use nodemon for hot reload
CMD ["npm", "run", "dev"]
'''
        elif language == "python":
            content = f'''# Development Dockerfile with hot reload
FROM python:{python_version}-slim

WORKDIR /app

# Set development environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT={port}

# Install dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy source (will be overridden by volume mount in dev)
COPY . .

EXPOSE {port}

# Use uvicorn with reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}", "--reload"]
'''
        else:
            content = f'''# Development Dockerfile
FROM node:{node_version}-alpine

WORKDIR /app

ENV NODE_ENV=development
ENV PORT={port}

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE {port}

CMD ["npm", "run", "dev"]
'''

        return TemplateResult(
            filename="Dockerfile.dev",
            content=content,
            language="dockerfile",
            path="",
            dependencies=[],
        )

    def generate_full_stack(
        self,
        app_name: str,
        language: str = "node",
        port: int = 3000,
        with_postgres: bool = True,
        with_redis: bool = True,
    ) -> GenerationResult:
        """Generate complete Docker setup for a full-stack application.

        Args:
            app_name: Application name
            language: Programming language
            port: Application port
            with_postgres: Include PostgreSQL
            with_redis: Include Redis

        Returns:
            All Docker configuration files
        """
        files = []

        # Production Dockerfile
        dockerfile = self.generate_dockerfile(
            language=language,
            app_name=app_name,
            port=port,
            multi_stage=True,
            with_healthcheck=True,
            with_non_root_user=True,
        )
        files.append(dockerfile)

        # Development Dockerfile
        dev_dockerfile = self.generate_dev_dockerfile(
            language=language,
            port=port,
        )
        files.append(dev_dockerfile)

        # Docker Compose
        compose = self.generate_compose(
            app_name=app_name,
            with_postgres=with_postgres,
            with_redis=with_redis,
            app_port=port,
            environment="production",
        )
        files.append(compose)

        # Development Compose
        dev_compose = self._generate_dev_compose(app_name, port, with_postgres, with_redis)
        files.append(dev_compose)

        # .dockerignore
        dockerignore = self.generate_dockerignore(language=language)
        files.append(dockerignore)

        instructions = f"""
## Docker Setup for {app_name}

### Development
```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up

# Rebuild after dependency changes
docker-compose -f docker-compose.dev.yml up --build
```

### Production
```bash
# Build production image
docker build -t {app_name}:latest .

# Start production environment
docker-compose up -d

# View logs
docker-compose logs -f {app_name}
```

### Services
- **{app_name}**: Main application on port {port}
{"- **PostgreSQL**: Database on port 5432" if with_postgres else ""}
{"- **Redis**: Cache on port 6379" if with_redis else ""}

### Environment Variables
Create a `.env` file:
```
NODE_ENV=production
PORT={port}
{"DATABASE_URL=postgresql://postgres:postgres@postgres:5432/app" if with_postgres else ""}
{"REDIS_URL=redis://redis:6379" if with_redis else ""}
```
"""

        return GenerationResult(
            files=files,
            instructions=instructions,
            dependencies={},
        )

    def _generate_dev_compose(
        self,
        app_name: str,
        port: int,
        with_postgres: bool,
        with_redis: bool,
    ) -> TemplateResult:
        """Generate development docker-compose file."""
        depends_on = []
        if with_postgres:
            depends_on.append("postgres")
        if with_redis:
            depends_on.append("redis")

        depends_section = ""
        if depends_on:
            depends_section = f"""
    depends_on:
{chr(10).join(f'      - {dep}' for dep in depends_on)}"""

        services = [f'''  {app_name}:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: {app_name}-dev
    ports:
      - "{port}:{port}"
    volumes:
      - .:/app
      - /app/node_modules
    environment:
      - NODE_ENV=development
      - PORT={port}
      {"- DATABASE_URL=postgresql://postgres:postgres@postgres:5432/app" if with_postgres else ""}
      {"- REDIS_URL=redis://redis:6379" if with_redis else ""}{depends_section}
    networks:
      - app-network''']

        if with_postgres:
            services.append('''  postgres:
    image: postgres:16-alpine
    container_name: postgres-dev
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - app-network''')

        if with_redis:
            services.append('''  redis:
    image: redis:7-alpine
    container_name: redis-dev
    ports:
      - "6379:6379"
    networks:
      - app-network''')

        volumes = []
        if with_postgres:
            volumes.append("postgres_dev_data:")

        volumes_section = ""
        if volumes:
            volumes_section = f'''
volumes:
  {chr(10).join(f'  {v}' for v in volumes)}'''

        content = f'''version: '3.8'

services:
{chr(10).join(services)}

networks:
  app-network:
    driver: bridge
{volumes_section}
'''

        return TemplateResult(
            filename="docker-compose.dev.yml",
            content=content,
            language="yaml",
            path="",
            dependencies=[],
        )
