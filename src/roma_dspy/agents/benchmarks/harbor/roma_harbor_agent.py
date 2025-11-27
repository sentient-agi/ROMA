"""
ROMA InstalledAgent for Harbor Framework.

Generic agent for running ROMA-DSPy on any Harbor dataset.
Configuration is driven by ROMA_PROFILE environment variable.

Key features:
- Uses Harbor's default Dockerfile (no custom Dockerfile needed)
- Comprehensive install script handles all setup (system deps, goofys, ROMA)
- Multi-container architecture with postgres, mlflow, minio
- E2B+Goofys file sync via S3
- Flat storage structure: /app -> /opt/sentient
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
        ROMA agent for Harbor Framework.

        Generic agent that works with any Harbor dataset. Configuration
        is driven entirely by the ROMA_PROFILE environment variable,
        which should specify a profile path like 'tb2/subprocess_v2' or
        'swe_bench/default'.

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
            - ROMA_PROFILE: Config profile path (e.g., 'tb2/subprocess_v2', 'swe_bench/default')
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

            Executes: /opt/roma-venv/bin/python -m roma_dspy.cli solve "instruction" --output json
            Writes result to /tmp/roma_result.json for metrics capture

            Profile name comes from ROMA_PROFILE environment variable (set by Harbor from job config).
            Supports subdirectory profiles like 'tb2/subprocess_v2' or 'swe_bench/default'.

            Args:
                instruction: Task instruction from Harbor

            Returns:
                List of ExecInput commands to execute
            """
            escaped_instruction = shlex.quote(instruction)

            # Environment for command execution
            # NOTE: API keys and most configuration comes from the task container's .env file
            # (loaded via docker-compose env_file). We only pass computed values and defaults here.
            # The container already has: OPENROUTER_API_KEY, E2B_API_KEY, ANTHROPIC_API_KEY, etc.
            env = {
                # Service URLs - provide defaults if not set in container
                # These use Docker service names for container-to-container communication
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@roma-dspy-postgres:5432/roma_dspy",
                "MLFLOW_TRACKING_URI": "http://roma-dspy-mlflow:5000",
                "MLFLOW_S3_ENDPOINT_URL": "http://roma-dspy-minio:9000",
                # Service flags - defaults
                "POSTGRES_ENABLED": "true",
                "MLFLOW_ENABLED": "true",
                # Runtime defaults
                "LOG_LEVEL": "INFO",
                "STORAGE_BASE_PATH": "/opt/sentient",
                "AWS_REGION": "us-east-1",
            }

            # Pass ROMA_PROFILE if set in host environment (from justfile profile override)
            # This overrides the default in container's .env
            roma_profile = os.environ.get("ROMA_PROFILE")
            if roma_profile:
                env["ROMA_PROFILE"] = roma_profile
                logger.info(f"Using profile override from host: {roma_profile}")
            else:
                logger.info("Using default profile from container .env")

            # Pass MLFLOW_EXPERIMENT_NAME if set in host environment (from justfile experiment override)
            mlflow_experiment = os.environ.get("MLFLOW_EXPERIMENT_NAME")
            if mlflow_experiment:
                env["MLFLOW_EXPERIMENT_NAME"] = mlflow_experiment
                logger.info(
                    f"Using MLflow experiment override from host: {mlflow_experiment}"
                )

            # Build command
            # Configuration read from environment variables (set by Harbor from job config)
            # No --profile argument needed - ConfigManager reads ROMA_PROFILE from environment
            cmd_parts = [
                "/opt/roma-venv/bin/python -m roma_dspy.cli solve",
                escaped_instruction,
                "--output json",
            ]

            # Pass max_depth if set in host environment (from justfile override)
            max_depth = os.environ.get("ROMA_MAX_DEPTH")
            if max_depth:
                cmd_parts.append(f"--max-depth {max_depth}")
                logger.info(f"Using max_depth override from host: {max_depth}")

            # Redirect output to result file
            cmd_parts.append("> /tmp/roma_result.json")

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

            except Exception as e:
                logger.error(f"Failed to parse result file: {e}")

else:
    # Placeholder when Harbor not installed

    class RomaHarborAgent:
        """Placeholder when Harbor not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Harbor is not installed. Install with: pip install harbor"
            )
