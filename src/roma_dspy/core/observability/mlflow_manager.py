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
            # IMPORTANT: Do NOT mutate self.config.enabled - it's a reference to the original config!
            # Instead, mark as not initialized and return early
            if not self._check_connectivity():
                logger.warning("MLflow connectivity check failed - tracing will be disabled")
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
            # Do NOT mutate self.config.enabled - just mark as not initialized
        except Exception as e:
            logger.error(f"Failed to initialize MLflow: {e}")
            # Do NOT mutate self.config.enabled - just mark as not initialized

    def _ensure_experiment(self, mlflow_mod) -> None:
        """Ensure the configured experiment is usable with robust error handling.

        Behavior:
        - Try to set experiment by name (happy path)
        - Handle state inconsistencies between MLflow cache and database
        - Migrate artifact locations from local to S3 if needed
        - Retry with exponential backoff for transient errors
        - Provide detailed diagnostics for troubleshooting
        """
        name = self.config.experiment_name
        max_retries = 3
        retry_delay = 0.5  # Start with 500ms

        for attempt in range(max_retries):
            try:
                mlflow_mod.set_experiment(name)
                exp = mlflow_mod.get_experiment_by_name(name)

                # Check if artifact location needs migration to S3
                if exp and not exp.artifact_location.startswith("s3://"):
                    logger.warning(
                        f"Experiment '{name}' uses legacy artifact location: {exp.artifact_location}. "
                        f"Consider migrating to S3 storage for consistency."
                    )

                logger.info(f"MLflow experiment set to: {name} (artifact_location: {exp.artifact_location})")
                return

            except Exception as e:
                error_msg = str(e)
                is_last_attempt = attempt == max_retries - 1

                # Log with appropriate level based on attempt
                if is_last_attempt:
                    logger.warning(f"set_experiment('{name}') failed on final attempt: {error_msg}")
                else:
                    logger.debug(f"set_experiment('{name}') failed (attempt {attempt + 1}/{max_retries}): {error_msg}")

                # Handle specific error cases
                if "deleted experiment" in error_msg.lower():
                    if self._handle_deleted_experiment_error(mlflow_mod, name):
                        continue  # Retry after recovery
                    elif not is_last_attempt:
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                elif not is_last_attempt:
                    # Retry for transient errors
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue

                # Last attempt failed, try comprehensive recovery
                if is_last_attempt:
                    if self._attempt_recovery(mlflow_mod, name):
                        return

                    # All recovery attempts failed
                    raise RuntimeError(
                        f"Failed to ensure MLflow experiment '{name}' after {max_retries} attempts. "
                        f"Last error: {error_msg}. Check MLflow server logs and database state."
                    )

    def _handle_deleted_experiment_error(self, mlflow_mod, name: str) -> bool:
        """Handle the specific case where MLflow reports an experiment as deleted.

        This can occur due to cache inconsistencies between MLflow server and database.

        Returns:
            True if recovery succeeded, False otherwise
        """
        try:
            from mlflow.tracking import MlflowClient
            try:
                from mlflow.entities import ViewType
            except Exception:
                from mlflow.entities.view_type import ViewType  # type: ignore

            client = MlflowClient(tracking_uri=self.config.tracking_uri)
            exps = client.search_experiments(view_type=ViewType.ALL)
            target = next((exp for exp in exps if exp.name == name), None)

            if target:
                lifecycle = getattr(target, "lifecycle_stage", "").lower()
                logger.info(
                    f"Found experiment '{name}' (ID: {target.experiment_id}, stage: {lifecycle}, "
                    f"artifact_location: {target.artifact_location})"
                )

                if lifecycle == "deleted":
                    # Truly deleted - try to restore or recreate
                    logger.info(f"Attempting to restore soft-deleted experiment '{name}' (ID: {target.experiment_id})")
                    try:
                        client.restore_experiment(target.experiment_id)
                        logger.info(f"Restored experiment '{name}' (ID: {target.experiment_id})")
                        mlflow_mod.set_experiment(name)
                        return True
                    except Exception as restore_err:
                        logger.warning(f"Restore failed ({restore_err}). Attempting delete and recreate...")
                        # If restore fails, try delete and recreate
                        try:
                            client.delete_experiment(target.experiment_id)
                            self._create_experiment_with_s3(client, mlflow_mod, name)
                            return True
                        except Exception as recreate_err:
                            logger.error(f"Delete and recreate failed: {recreate_err}")
                            return False

                elif lifecycle == "active":
                    # Database shows active but MLflow reports deleted - cache inconsistency
                    logger.warning(
                        f"Experiment '{name}' is active in database but MLflow reports it as deleted. "
                        f"This indicates a cache inconsistency. Attempting to resolve..."
                    )

                    # Try migrating artifact location if it's using legacy local storage
                    if not target.artifact_location.startswith("s3://"):
                        logger.info(f"Migrating experiment '{name}' from local to S3 storage")
                        try:
                            # Delete and recreate with S3 storage
                            client.delete_experiment(target.experiment_id)
                            self._create_experiment_with_s3(client, mlflow_mod, name)
                            return True
                        except Exception as migrate_err:
                            logger.warning(f"Migration failed: {migrate_err}")

                    # Fallback: force refresh by trying set_experiment again
                    try:
                        mlflow_mod.set_experiment(name)
                        return True
                    except Exception:
                        logger.debug("Force refresh failed")
                        return False
                else:
                    logger.warning(f"Unexpected lifecycle stage '{lifecycle}' for experiment '{name}'")
                    return False
            else:
                # Experiment not found - create it
                logger.info(f"Experiment '{name}' not found. Creating new experiment.")
                return self._create_experiment_with_s3(client, mlflow_mod, name)

        except Exception as e:
            logger.error(f"Error handling deleted experiment: {e}")
            return False

    def _create_experiment_with_s3(self, client, mlflow_mod, name: str) -> bool:
        """Create a new experiment with S3 artifact storage.

        Returns:
            True if creation succeeded, False otherwise
        """
        import os
        artifact_root = os.environ.get("MLFLOW_DEFAULT_ARTIFACT_ROOT", "s3://mlflow")

        try:
            exp_id = client.create_experiment(name, artifact_location=artifact_root)
            experiment = client.get_experiment(exp_id)
            logger.info(
                f"Created MLflow experiment '{name}' (ID: {exp_id}) with artifact storage: {experiment.artifact_location}"
            )
            mlflow_mod.set_experiment(name)
            return True
        except Exception as ce:
            # Handle duplicate experiment name error
            if "already exists" in str(ce).lower():
                logger.info(f"Experiment '{name}' already exists. Setting as active.")
                try:
                    mlflow_mod.set_experiment(name)
                    return True
                except Exception:
                    return False
            else:
                logger.error(f"Failed to create experiment: {ce}")
                return False

    def _attempt_recovery(self, mlflow_mod, name: str) -> bool:
        """Final comprehensive recovery attempt for experiment setup.

        Returns:
            True if recovery succeeded, False otherwise
        """
        try:
            logger.info(f"Attempting comprehensive recovery for experiment '{name}'")
            from mlflow.tracking import MlflowClient

            client = MlflowClient(tracking_uri=self.config.tracking_uri)

            # Try to create or set the experiment one final time
            try:
                if self._create_experiment_with_s3(client, mlflow_mod, name):
                    return True
            except Exception as e:
                logger.debug(f"Final recovery attempt failed: {e}")

            # Last resort: try to use the Default experiment
            try:
                logger.warning(f"All recovery attempts failed. Falling back to 'Default' experiment.")
                mlflow_mod.set_experiment("Default")
                logger.info("Successfully set to 'Default' experiment as fallback")
                return True
            except Exception as e:
                logger.error(f"Even 'Default' experiment failed: {e}")

        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")

        return False

    

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
