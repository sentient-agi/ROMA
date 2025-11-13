"""
ROMA InstalledAgent for Harbor Framework (Terminal-Bench 2.0).

Key features:
- Uses Harbor's default Dockerfile (no custom Dockerfile needed)
- Comprehensive install script handles all setup (system deps, goofys, ROMA)
- Multi-container architecture with postgres, mlflow, minio
- E2B+Goofys file sync via S3
- Flat storage structure: /app → /opt/sentient
"""

import json
import os
import shlex
from pathlib import Path
from typing import List

from loguru import logger

try:
    from harbor.agents.installed.base import BaseInstalledAgent, ExecInput
    from harbor.models.agent.context import AgentContext
    HARBOR_AVAILABLE = True
except ImportError:
    HARBOR_AVAILABLE = False
    logger.warning(
        "Harbor not installed. RomaHarborAgent will not be available. "
        "Install with: pip install harbor"
    )


if HARBOR_AVAILABLE:

    class RomaHarborAgent(BaseInstalledAgent):
        """
        ROMA agent for Harbor Framework (Terminal-Bench 2.0).

        Architecture:
        - Installed inside task container (Harbor's default Dockerfile)
        - Install script sets up: goofys, S3 mount, symlink, services, ROMA
        - Uses E2BToolkit for code execution
        - Goofys mounts S3 to /opt/sentient in both task container and E2B
        - Auto-sync between containers via S3 (1-2s latency)

        Benefits:
        - Clean multi-container setup via docker-compose
        - No manual network injection
        - E2B code execution with file sync
        - Full ROMA capabilities
        - Token metrics and trajectory capture
        """

        @staticmethod
        def name() -> str:
            """Return agent name for Harbor registry."""
            return "roma-dspy"

        @staticmethod
        def version() -> str:
            """Return agent version."""
            return "2.0.0"

        def __init__(self, **kwargs):
            """
            Initialize ROMA Harbor Agent.

            Configuration from environment variables (set by Harbor from job config):
            - ROMA_PROFILE: Config profile (default: terminal_bench_v2)
            - ROMA_MAX_DEPTH: Maximum recursion depth
            - STORAGE_BASE_PATH: Storage base path (default: /opt/sentient)

            Note: Configuration is read from container environment at runtime,
            not from host environment during initialization.
            """
            super().__init__(**kwargs)

        @property
        def _install_agent_template_path(self) -> Path:
            """Path to Jinja2 installation template."""
            return Path(__file__).parent / "install-roma.sh.j2"

        def create_run_agent_commands(
            self,
            instruction: str,
        ) -> List[ExecInput]:
            """
            Generate commands to run ROMA agent.

            Executes: /opt/roma-venv/bin/python -m roma_dspy.cli solve "instruction" --profile <profile> --output json
            Writes result to /tmp/roma_result.json for metrics capture

            Profile name comes from ROMA_PROFILE environment variable (set by Harbor from job config).
            All other configuration (max_depth, storage, etc.) comes from the profile config file.

            Args:
                instruction: Task instruction from Harbor

            Returns:
                List of ExecInput commands to execute
            """
            escaped_instruction = shlex.quote(instruction)

            # Split credentials: real S3 for goofys/E2B, MinIO for MLflow artifacts
            s3_access_key = (
                os.environ.get("AWS_ACCESS_KEY_ID_S3")
                or os.environ.get("AWS_ACCESS_KEY_ID")
            )
            s3_secret_key = (
                os.environ.get("AWS_SECRET_ACCESS_KEY_S3")
                or os.environ.get("AWS_SECRET_ACCESS_KEY")
            )
            minio_access_key = (
                os.environ.get("AWS_ACCESS_KEY_ID_MINIO")
                or os.environ.get("MINIO_ROOT_USER")
                or os.environ.get("AWS_ACCESS_KEY_ID")
            )
            minio_secret_key = (
                os.environ.get("AWS_SECRET_ACCESS_KEY_MINIO")
                or os.environ.get("MINIO_ROOT_PASSWORD")
                or os.environ.get("AWS_SECRET_ACCESS_KEY")
            )

            # Log credential sources for debugging
            logger.info(
                f"Agent credentials from HOST environment: "
                f"minio_access_key={minio_access_key[:10] if minio_access_key else None}..., "
                f"AWS_ACCESS_KEY_ID_MINIO={os.environ.get('AWS_ACCESS_KEY_ID_MINIO')}, "
                f"MINIO_ROOT_USER={os.environ.get('MINIO_ROOT_USER')}, "
                f"AWS_ACCESS_KEY_ID={os.environ.get('AWS_ACCESS_KEY_ID')[:10] if os.environ.get('AWS_ACCESS_KEY_ID') else None}..."
            )

            # Environment for command execution
            env = {
                # Profile configuration (CRITICAL: must be passed to container)
                "ROMA_PROFILE": os.environ.get("ROMA_PROFILE"),

                # API Keys
                "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
                "E2B_API_KEY": os.environ.get("E2B_API_KEY"),
                "E2B_TEMPLATE_ID": os.environ.get("E2B_TEMPLATE_ID"),
                "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
                "FIREWORKS_API_KEY": os.environ.get("FIREWORKS_API_KEY"),

                # S3 Storage (only override if explicitly set in job config)
                "STORAGE_BASE_PATH": os.environ.get("STORAGE_BASE_PATH"),
                "ROMA_S3_BUCKET": os.environ.get("ROMA_S3_BUCKET"),
                "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
                # Provide both credential sets so install script can swap safely
                "AWS_ACCESS_KEY_ID_S3": s3_access_key,
                "AWS_SECRET_ACCESS_KEY_S3": s3_secret_key,
                # Default AWS env vars reserved for MinIO (MLflow artifacts)
                "AWS_ACCESS_KEY_ID": minio_access_key,
                "AWS_SECRET_ACCESS_KEY": minio_secret_key,
                "AWS_ACCESS_KEY_ID_MINIO": minio_access_key,
                "AWS_SECRET_ACCESS_KEY_MINIO": minio_secret_key,

                # Service URLs - let Harbor job config provide these (don't override)
                # Only include if explicitly set in host environment
                "DATABASE_URL": os.environ.get("DATABASE_URL"),
                "MLFLOW_TRACKING_URI": os.environ.get("MLFLOW_TRACKING_URI"),
                "MLFLOW_S3_ENDPOINT_URL": os.environ.get("MLFLOW_S3_ENDPOINT_URL"),

                # Service flags
                "POSTGRES_ENABLED": os.environ.get("POSTGRES_ENABLED", "true"),
                "MLFLOW_ENABLED": os.environ.get("MLFLOW_ENABLED", "true"),

                # Runtime configuration (not in profile)
                "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            }

            # Log and filter out None values (Harbor's ExecInput requires all env values to be strings)
            none_vars = [k for k, v in env.items() if v is None]
            if none_vars:
                logger.warning(f"Environment variables not set (will be excluded): {', '.join(none_vars)}")
            env = {k: v for k, v in env.items() if v is not None}

            # Build command
            # Configuration read from environment variables (set by Harbor from job config)
            # No --profile argument needed - ConfigManager reads ROMA_PROFILE from environment
            cmd_parts = [
                "/opt/roma-venv/bin/python -m roma_dspy.cli solve",
                escaped_instruction,
                "--output json",
                "> /tmp/roma_result.json",
            ]

            command = " ".join(cmd_parts)

            logger.info("Running ROMA with config from environment variables")

            return [
                ExecInput(
                    command=command,
                    working_dir="/app",
                    env=env,
                    timeout=3600,  # 1 hour
                )
            ]

        def populate_context_post_run(
            self,
            context: AgentContext,
        ) -> None:
            """
            Parse trajectory and update context.

            Reads /tmp/roma_result.json and extracts:
            - Token metrics (input/output tokens)
            - Execution status
            - Trajectory (optional, for ATIF format)

            Args:
                context: Agent context to populate
            """
            result_file = Path("/tmp/roma_result.json")

            if not result_file.exists():
                logger.warning("Result file not found - using default context")
                return

            try:
                # Read result JSON
                result_data = json.loads(result_file.read_text())

                # Extract token metrics
                context.total_input_tokens = result_data.get("total_input_tokens", 0)
                context.total_output_tokens = result_data.get("total_output_tokens", 0)

                # Extract status
                status = result_data.get("status", "completed")

                logger.info(
                    f"Token usage: input={context.total_input_tokens}, "
                    f"output={context.total_output_tokens}, status={status}"
                )

                # Optional: Convert ROMA trace to ATIF format
                # TODO: Implement ROMA -> ATIF conversion (defer to Phase 7)
                # if "trace_id" in result_data:
                #     trajectory = self._convert_trace_to_atif(result_data["trace_id"])
                #     context.trajectory = trajectory

            except Exception as e:
                logger.error(f"Failed to parse result file: {e}")

else:
    # Placeholder when Harbor not installed

    class RomaHarborAgent:
        """Placeholder when Harbor not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Harbor is not installed. "
                "Install with: pip install harbor"
            )
