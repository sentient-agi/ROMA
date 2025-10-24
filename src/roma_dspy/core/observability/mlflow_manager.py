"""MLflow tracing manager for ROMA-DSPy."""

from contextlib import contextmanager
from typing import Optional, Dict, Any

import dspy
from loguru import logger

from roma_dspy.config.schemas.observability import MLflowConfig
from roma_dspy.core.observability.tool_span_callback import ROMAToolSpanCallback


class MLflowManager:
    """Manages MLflow tracing lifecycle for ROMA-DSPy.

    Provides automatic tracing for DSPy programs with minimal setup.
    Handles initialization, run management, and metric logging.
    """

    def __init__(self, config: MLflowConfig):
        """Initialize MLflow manager.

        Args:
            config: MLflow configuration
        """
        self.config = config
        self._initialized = False
        self._mlflow = None

    def _check_connectivity(self) -> bool:
        """Check if MLflow server is reachable.

        Be tolerant of servers without a /health endpoint. Consider the server
        reachable if either a HEAD/GET to the tracking URI returns a non-5xx
        status, or a GET to /health succeeds.

        Returns:
            True if server appears reachable, False otherwise
        """
        # Skip connectivity check for file:// URIs (local storage doesn't need a server)
        if self.config.tracking_uri.startswith("file://"):
            logger.debug("MLflow using file:// URI, skipping connectivity check")
            return True

        try:
            import requests

            base = self.config.tracking_uri.rstrip("/")
            probes = [
                ("HEAD", base),
                ("GET", f"{base}/health"),
                ("GET", base),
            ]

            for method, url in probes:
                try:
                    resp = requests.request(method, url, timeout=2)
                    # Treat any non-5xx as acceptable (e.g., 200/302/404 on /health)
                    if resp.status_code < 500:
                        logger.debug(f"MLflow reachable via {method} {url} -> {resp.status_code}")
                        return True
                except Exception:
                    continue

            logger.warning(
                f"MLflow server not reachable at {self.config.tracking_uri}. "
                f"Disabling MLflow tracking. Start MLflow with: docker compose --profile observability up"
            )
            return False
        except ImportError:
            logger.warning("requests not installed; skipping connectivity probe")
            return True

    def initialize(self) -> None:
        """Initialize MLflow tracking and autolog.

        This must be called before using MLflow features.
        Safe to call multiple times - subsequent calls are no-ops.
        """
        if self._initialized:
            logger.debug("MLflow already initialized, skipping")
            return

        if not self.config.enabled:
            logger.info("MLflow tracing disabled in config")
            return

        try:
            import mlflow

            self._mlflow = mlflow

            # Set tracking URI
            mlflow.set_tracking_uri(self.config.tracking_uri)
            logger.info(f"MLflow tracking URI set to: {self.config.tracking_uri}")

            # Check connectivity before attempting to set experiment
            if not self._check_connectivity():
                self.config.enabled = False
                return

            # Ensure experiment exists and is active (restore if soft-deleted; create if missing)
            self._ensure_experiment(mlflow)

            # Enable DSPy autolog
            mlflow.dspy.autolog(
                log_traces=self.config.log_traces,
                log_traces_from_compile=self.config.log_traces_from_compile,
                log_traces_from_eval=self.config.log_traces_from_eval,
                log_compiles=self.config.log_compiles,
                log_evals=self.config.log_evals
            )
            logger.info("MLflow DSPy autolog enabled")

            # Register ROMA callback to enhance MLflow's Tool.* spans
            # Must happen AFTER autolog so we don't replace MLflow's callback
            try:
                roma_callback = ROMAToolSpanCallback()
                callbacks = dspy.settings.get("callbacks", [])  # Get existing (includes MLflow's)
                callbacks.append(roma_callback)  # Add ROMA callback
                dspy.settings.configure(callbacks=callbacks)
                logger.info("ROMA tool span enhancement callback registered")
            except Exception as e:
                logger.warning(f"Failed to register ROMA callback: {e}. Tool spans will not have ROMA attributes")

            self._initialized = True
            logger.info("MLflow tracing initialized successfully")

        except ImportError:
            logger.error("mlflow package not installed. Run: pip install mlflow>=2.18.0")
            self.config.enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize MLflow: {e}")
            self.config.enabled = False

    def _ensure_experiment(self, mlflow_mod) -> None:
        """Ensure the configured experiment is usable.

        Behavior:
        - Try to set experiment by name (happy path)
        - If it fails due to soft-deleted or missing experiment, attempt to restore or create
        - Prefer HTTP-served artifact root for new experiments (mlflow-artifacts:/<name>)
        """
        name = self.config.experiment_name

        try:
            mlflow_mod.set_experiment(name)
            logger.info(f"MLflow experiment set to: {name}")
            return
        except Exception as e:
            logger.warning(f"set_experiment('{name}') failed: {e}. Attempting auto-recovery…")

        try:
            from mlflow.tracking import MlflowClient
            try:
                # ViewType import path differs across mlflow versions; handle gracefully
                from mlflow.entities import ViewType  # mlflow <3.6
            except Exception:
                from mlflow.entities.view_type import ViewType  # type: ignore

            client = MlflowClient(tracking_uri=self.config.tracking_uri)
            exps = client.search_experiments(view_type=ViewType.ALL)
            target = next((exp for exp in exps if exp.name == name), None)

            if target:
                lifecycle = getattr(target, "lifecycle_stage", "").lower()
                if lifecycle == "deleted":
                    # Permanently delete soft-deleted experiment and recreate with S3 storage
                    logger.info(f"Found soft-deleted experiment '{name}' (ID: {target.experiment_id}). Permanently deleting to recreate with S3 storage...")
                    try:
                        # Permanently delete from database
                        client.delete_experiment(target.experiment_id)
                        logger.info(f"Permanently deleted experiment '{name}' (ID: {target.experiment_id})")
                    except Exception as del_err:
                        logger.warning(f"Could not permanently delete experiment: {del_err}. Will try to create anyway.")
                    # Fall through to create new experiment below
                else:
                    # Exists and is active but set_experiment failed – re-raise for visibility
                    raise RuntimeError(
                        f"Experiment '{name}' exists (stage={lifecycle}) but could not be activated."
                    )

            # Not found or was deleted: create with S3 artifact root (uses MinIO for local dev, AWS S3 for prod)
            # Explicitly set artifact_location to ensure S3 storage is used
            import os
            artifact_root = os.environ.get("MLFLOW_DEFAULT_ARTIFACT_ROOT", "s3://mlflow")
            try:
                exp_id = client.create_experiment(name, artifact_location=artifact_root)
                experiment = client.get_experiment(exp_id)
                logger.info(
                    f"Created MLflow experiment '{name}' at {experiment.artifact_location} and set active"
                )
            except Exception as ce:
                logger.warning(f"create_experiment failed for '{name}': {ce}. Falling back to set_experiment")

            # Final attempt to set
            mlflow_mod.set_experiment(name)
            return

        except Exception as e:
            # Surface a clear error with guidance
            raise RuntimeError(
                "Failed to ensure MLflow experiment. Either restore the soft-deleted experiment, "
                "choose a new experiment name, or permanently delete the old one. Details: "
                f"{e}"
            )

    

    @contextmanager
    def trace_execution(
        self,
        execution_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Context manager for tracing execution runs.

        Args:
            execution_id: Unique execution identifier (used as run name)
            metadata: Optional metadata to log as parameters

        Example:
            with mlflow_manager.trace_execution("exec_123", {"depth": 5}):
                result = solver.solve(task)
        """
        if not self.config.enabled or not self._initialized:
            yield None
            return

        try:
            with self._mlflow.start_run(run_name=execution_id) as run:
                # Enhanced tagging for better correlation
                tags = {
                    "execution_id": execution_id,
                    "roma_version": "0.1.0",
                    "solver_type": "RecursiveSolver",
                    "framework": "ROMA-DSPy",
                }

                # Add metadata as tags with prefix
                if metadata:
                    for key, value in metadata.items():
                        tags[f"meta.{key}"] = str(value)

                # Set tags
                try:
                    self._mlflow.set_tags(tags)
                    logger.debug(f"Set MLflow tags for execution: {execution_id}")
                except Exception as e:
                    logger.warning(f"Failed to set MLflow tags: {e}")

                # Log metadata as parameters (separate from tags)
                if metadata:
                    try:
                        self._mlflow.log_params(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to log parameters: {e}")

                yield run

        except Exception as e:
            logger.error(f"Error in MLflow trace context: {e}")
            yield None

    def log_metrics(self, metrics: Dict[str, float]) -> None:
        """Log execution metrics.

        Args:
            metrics: Dictionary of metric names to values
        """
        if not self.config.enabled or not self._initialized:
            return

        try:
            self._mlflow.log_metrics(metrics)
            logger.debug(f"Logged metrics: {list(metrics.keys())}")
        except Exception as e:
            logger.warning(f"Failed to log metrics: {e}")

    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None) -> None:
        """Log artifact file.

        Args:
            local_path: Path to local file to log
            artifact_path: Optional path within artifact store
        """
        if not self.config.enabled or not self._initialized:
            return

        try:
            self._mlflow.log_artifact(local_path, artifact_path)
            logger.debug(f"Logged artifact: {local_path}")
        except Exception as e:
            logger.warning(f"Failed to log artifact {local_path}: {e}")

    def log_param(self, key: str, value: Any) -> None:
        """Log a single parameter.

        Args:
            key: Parameter name
            value: Parameter value
        """
        if not self.config.enabled or not self._initialized:
            return

        try:
            self._mlflow.log_param(key, value)
        except Exception as e:
            logger.warning(f"Failed to log param {key}: {e}")

    def shutdown(self) -> None:
        """Cleanup MLflow resources.

        Ends any active runs and performs cleanup.
        """
        if not self._initialized:
            return

        try:
            if self._mlflow:
                self._mlflow.end_run()
            logger.info("MLflow tracing shutdown complete")
        except Exception as e:
            logger.warning(f"Error during MLflow shutdown: {e}")
        finally:
            self._initialized = False
