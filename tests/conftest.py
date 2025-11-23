"""Pytest configuration and helpers for ROMA DSPy tests."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

# Configure DSPy cache directory before importing DSPy modules
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".dspy_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

cache_path = str(_CACHE_DIR)
os.environ.setdefault("DSPY_CACHEDIR", cache_path)
os.environ.setdefault("DSPY_CACHE_DIR", cache_path)

import pytest
import pytest_asyncio
from loguru import logger

from roma_dspy import SubTask
from roma_dspy.types import NodeType, PredictionStrategy, TaskType


def _build_response(signature: Any, payload: Dict[str, Any]) -> Any:
    name = getattr(signature, "__name__", str(signature))

    if name == "AtomizerSignature":
        goal = payload.get("goal", "").lower()
        is_atomic = goal.startswith("atomic")
        node_type = NodeType.EXECUTE if is_atomic else NodeType.PLAN
        return SimpleNamespace(is_atomic=is_atomic, node_type=node_type)

    if name == "PlannerSignature":
        goal = payload.get("goal", "")
        subtasks = [
            SubTask(
                goal=f"{goal} -> step 1", task_type=TaskType.THINK, dependencies=[]
            ),
            SubTask(
                goal=f"{goal} -> step 2",
                task_type=TaskType.WRITE,
                dependencies=["step 1"],
            ),
        ]
        dependencies = {"step 2": ["step 1"]}
        return SimpleNamespace(subtasks=subtasks, dependencies_graph=dependencies)

    if name == "ExecutorSignature":
        goal = payload.get("goal", "")
        return SimpleNamespace(output=f"executed:{goal}", sources=["stub-source"])

    if name == "AggregatorResult":
        subtasks = payload.get("subtasks_results", [])
        combined = " | ".join(getattr(item, "goal", str(item)) for item in subtasks)
        return SimpleNamespace(synthesized_result=combined or "no subtasks provided")

    if name == "VerifierSignature":
        candidate = payload.get("candidate_output", "")
        verdict = "fail" not in candidate.lower()
        feedback = None if verdict else "Output flagged by verifier"
        return SimpleNamespace(verdict=verdict, feedback=feedback)

    raise ValueError(f"Unhandled signature '{name}' in test stub")


@pytest.fixture(autouse=True)
def stub_prediction_strategy(monkeypatch: pytest.MonkeyPatch):
    class DummyPredictor:
        def __init__(
            self, signature: Any, strategy: PredictionStrategy, **kwargs: Any
        ) -> None:
            self.signature = signature
            self.strategy = strategy
            self.build_kwargs = kwargs
            self.calls = []

        def _respond(self, kwargs: Dict[str, Any]) -> Any:
            self.calls.append(kwargs)
            return _build_response(self.signature, kwargs)

        def forward(self, **kwargs: Any) -> Any:
            return self._respond(kwargs)

        async def acall(self, **kwargs: Any) -> Any:
            return self._respond(kwargs)

        def __call__(self, **kwargs: Any) -> Any:
            return self.forward(**kwargs)

    def build(
        self: PredictionStrategy, signature: Any, **kwargs: Any
    ) -> DummyPredictor:
        return DummyPredictor(signature=signature, strategy=self, **kwargs)

    monkeypatch.setattr(PredictionStrategy, "build", build)
    yield


@pytest.fixture
def caplog_loguru(caplog):
    """Pytest fixture to capture loguru logs using pytest-loguru.

    This fixture enables capturing logs from loguru for testing purposes.
    It propagates loguru logs to the standard logging system so they can
    be captured by pytest's caplog fixture.

    Usage:
        def test_logging(caplog_loguru):
            logger.info("Test message")
            assert "Test message" in caplog_loguru.text

    Returns:
        pytest.LogCaptureFixture: The caplog fixture with loguru integration
    """
    import logging

    class PropagateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(PropagateHandler(), format="{message}")
    yield caplog
    logger.remove(handler_id)


@pytest.fixture
def clean_loguru():
    """Fixture to clean loguru handlers before and after tests.

    Ensures tests start with a clean slate and don't interfere with each other.
    """
    logger.remove()  # Remove all existing handlers
    yield
    logger.remove()  # Clean up after test


# ============================================================================
# API Test Fixtures
# ============================================================================


@pytest.fixture
def mock_execution():
    """Create a mock Execution model for API tests."""
    from datetime import datetime, timezone
    from roma_dspy.core.storage.models import Execution

    return Execution(
        execution_id="test-exec-123",
        status="running",
        initial_goal="Test task",  # Match test expectation
        max_depth=2,
        profile="default",  # Required field
        experiment_name="test-experiment",  # Required field
        total_tasks=10,
        completed_tasks=5,
        failed_tasks=0,
        config={"test": "config"},
        execution_metadata={"test": "metadata"},
        # dag_snapshot removed - now sourced from checkpoints
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_checkpoint():
    """Create a mock Checkpoint model for API tests."""
    from datetime import datetime, timezone
    from roma_dspy.core.storage.models import Checkpoint

    return Checkpoint(
        checkpoint_id="test-checkpoint-123",
        execution_id="test-exec-123",
        created_at=datetime.now(timezone.utc),
        trigger="manual",
        state="saved",
        dag_snapshot={"dag_id": "test-dag", "nodes": [], "edges": []},
        preserved_results={},
        module_states={},
        failed_task_ids=[],
        file_path="/tmp/checkpoint.json",
        file_size_bytes=1024,
        compressed=True,
    )


@pytest.fixture
def mock_storage(mock_execution, mock_checkpoint):
    """Create a mock PostgresStorage for API tests."""
    from unittest.mock import AsyncMock
    from roma_dspy.core.storage.postgres_storage import PostgresStorage

    storage = AsyncMock(spec=PostgresStorage)

    # Mock common methods
    storage.create_execution = AsyncMock(return_value=mock_execution)
    storage.get_execution = AsyncMock(return_value=mock_execution)
    storage.update_execution = AsyncMock(return_value=None)
    storage.list_executions = AsyncMock(return_value=[mock_execution])
    storage.count_executions = AsyncMock(return_value=1)

    # Create mock CheckpointData with proper root_dag structure
    # Use a simple namespace that has root_dag as a dict (helpers.py reads it as dict)
    from unittest.mock import MagicMock

    checkpoint_data = MagicMock()
    checkpoint_data.checkpoint_id = "test-checkpoint-123"
    checkpoint_data.execution_id = "test-exec-123"
    checkpoint_data.root_dag = {
        "dag_id": "test-dag",
        "nodes": [],
        "edges": [],
        "statistics": {},
    }

    storage.list_checkpoints = AsyncMock(return_value=[mock_checkpoint])
    storage.get_latest_checkpoint = AsyncMock(return_value=checkpoint_data)
    storage.load_checkpoint = AsyncMock(return_value=None)
    storage.delete_checkpoint = AsyncMock(return_value=True)

    storage.get_lm_traces = AsyncMock(return_value=[])
    storage.get_execution_costs = AsyncMock(
        return_value={"total_cost_usd": 0.0, "total_tokens": 0, "traces_count": 0}
    )

    storage.initialize = AsyncMock(return_value=None)
    storage.close = AsyncMock(return_value=None)

    return storage


@pytest.fixture
def mock_config_manager():
    """Create a mock ConfigManager for API tests."""
    from unittest.mock import MagicMock
    from roma_dspy.config.manager import ConfigManager

    manager = MagicMock(spec=ConfigManager)

    # Mock config object
    mock_config = MagicMock()
    mock_config.project = "roma-dspy"
    mock_config.version = "0.1.0"
    mock_config.storage.postgres.enabled = True
    mock_config.storage.postgres.connection_url = "postgresql+asyncpg://localhost/test"
    mock_config.model_dump.return_value = {"test": "config"}

    manager.load_config.return_value = mock_config

    return manager


@pytest.fixture
def mock_execution_service(mock_execution):
    """Create a mock ExecutionService for API tests."""
    from unittest.mock import AsyncMock
    from roma_dspy.api.execution_service import ExecutionService

    service = AsyncMock(spec=ExecutionService)

    # Mock start_execution to return execution_id
    async def mock_start(**kwargs):
        return mock_execution.execution_id  # Access as attribute, not dict

    service.start_execution = AsyncMock(side_effect=mock_start)

    # Mock get_execution_status
    service.get_execution_status = AsyncMock(
        return_value={"status": "running", "progress": 0.5}
    )

    # Mock cancel_execution
    service.cancel_execution = AsyncMock(return_value=True)

    return service


@pytest.fixture
def test_app(mock_storage, mock_config_manager, mock_execution_service):
    """Create FastAPI test application with mocked dependencies."""
    from datetime import datetime, timezone
    from roma_dspy.api.main import create_app

    app = create_app(enable_rate_limit=False)

    # Override app state with mocks
    class MockAppState:
        def __init__(self):
            self.storage = mock_storage
            self.config_manager = mock_config_manager
            self.execution_service = mock_execution_service
            self.startup_time = datetime.now(timezone.utc)

    app.state.app_state = MockAppState()

    return app


@pytest_asyncio.fixture
async def client(test_app):
    """Create async HTTP client for testing API endpoints."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
