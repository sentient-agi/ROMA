"""MLflow data access layer for fetching traces."""

from typing import Any, List, Optional, Set

from loguru import logger


class MLflowClient:
    """
    Data access layer for fetching MLflow traces.

    Responsibilities:
    - Fetch traces from MLflow by execution_id
    - Handle multiple search strategies (run tags, trace tags)
    - Return raw MLflow trace objects

    Does NOT handle:
    - Data consolidation (that's ExecutionDataService)
    - Data formatting (that's LLMTraceVisualizer)
    """

    def __init__(
        self,
        tracking_uri: Optional[str] = None,
    ):
        """
        Initialize MLflow client.

        Args:
            tracking_uri: MLflow tracking server URI (defaults to MLFLOW_TRACKING_URI env var)
        """
        self.tracking_uri = tracking_uri
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Lazy-load the MLflow client."""
        if self._client is None:
            from mlflow.tracking import MlflowClient as MLflowTrackingClient

            self._client = MLflowTrackingClient(tracking_uri=self.tracking_uri)
        return self._client

    def fetch_traces(self, execution_id: str) -> List[Any]:
        """
        Fetch all MLflow traces for the given execution_id.

        Strategy:
        1) Find runs where run name equals the execution_id or the tag 'execution_id' matches.
        2) Query traces scoped by those run_ids with include_spans=True so span data is present.
        3) If none found via run_id scoping, fall back to scanning experiments and filtering by
           trace tags ('execution_id' or 'mlflow.trace.session').

        Args:
            execution_id: Execution ID to search for

        Returns:
            List of MLflow trace objects (with spans)

        Raises:
            ValueError: If no traces found or fetch fails

        Note:
            include_spans=True requires experiments to use an HTTP-served artifact root
            (e.g., mlflow-artifacts:/). Old experiments with container-local paths won't return spans
            to the client.
        """
        try:
            # Search all experiments for runs with execution_id tag
            experiments = self.client.search_experiments()
            exp_ids = [exp.experiment_id for exp in experiments]

            # Step 1: find matching runs
            matching_run_ids: Set[str] = set()
            for exp_id in exp_ids:
                # Some servers don't support OR in filter; query twice
                for flt in [
                    f"tags.execution_id = '{execution_id}'",
                    f"tags.mlflow.runName = '{execution_id}'",
                ]:
                    try:
                        runs = self.client.search_runs(
                            [exp_id], filter_string=flt, max_results=200
                        )
                        for r in runs:
                            rid = getattr(getattr(r, "info", r), "run_id", None)
                            if rid:
                                matching_run_ids.add(rid)
                    except Exception:
                        # ignore invalid filter errors per server
                        continue

            logger.debug(
                f"Found {len(matching_run_ids)} matching runs for execution_id={execution_id}"
            )

            # Step 2: collect traces for those runs (with spans)
            collected: List[Any] = []
            for rid in matching_run_ids:
                try:
                    # Scope by the run's own experiment to avoid cross-experiment issues
                    try:
                        run = self.client.get_run(rid)
                        run_exp_ids = [run.info.experiment_id]
                    except Exception:
                        run_exp_ids = exp_ids
                    traces = self.client.search_traces(
                        experiment_ids=run_exp_ids, run_id=rid, include_spans=True
                    )
                    collected.extend(traces)
                except Exception:
                    # if run-scoped fetch fails, continue
                    continue

            if collected:
                logger.info(f"Fetched {len(collected)} traces via run-scoped search")
                return collected

            # Step 3: fallback — scan each experiment and filter by trace tags
            logger.debug(
                "No traces found via run-scoped search, trying fallback trace tag scan"
            )
            all_traces: List[Any] = []
            for exp_id in exp_ids:
                try:
                    traces = self.client.search_traces(
                        experiment_ids=[exp_id], include_spans=True
                    )
                except Exception:
                    # try without spans
                    try:
                        traces = self.client.search_traces(experiment_ids=[exp_id])
                    except Exception:
                        continue

                for t in traces:
                    info = getattr(t, "info", None)
                    tags = getattr(info, "tags", {}) if info else {}
                    if isinstance(tags, dict) and (
                        tags.get("execution_id") == execution_id
                        or tags.get("mlflow.trace.session") == execution_id
                    ):
                        all_traces.append(t)

            if not all_traces:
                raise ValueError(
                    f"No MLflow traces found for execution {execution_id}. "
                    f"Ensure the MLflow experiment stores artifacts via mlflow-artifacts:/ and that "
                    f"run name or tags include the execution_id."
                )

            logger.info(f"Fetched {len(all_traces)} traces via fallback tag scan")
            return all_traces

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to fetch MLflow traces: {e}")
