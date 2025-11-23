"""
Comprehensive SDK/Library usage tests.

Tests that ROMA-DSPy works as a library for developers.
Validates the public API and common usage patterns.

Run with:
    pytest tests/test_sdk_usage.py -v
    uv run pytest tests/test_sdk_usage.py -v
"""

import pytest
import os
from pathlib import Path


class TestSDKImports:
    """Test that SDK can be imported in various ways."""

    def test_top_level_import(self):
        """Should be able to import from top level."""
        from roma_dspy import solve

        assert solve is not None

    def test_engine_imports(self):
        """Should be able to import engine components."""
        from roma_dspy.core.engine import TaskDAG
        from roma_dspy.core.engine.solve import RecursiveSolver, solve
        from roma_dspy.core.engine.runtime import ModuleRuntime

        assert TaskDAG is not None
        assert RecursiveSolver is not None
        assert solve is not None
        assert ModuleRuntime is not None

    def test_module_imports(self):
        """Should be able to import all module types."""
        from roma_dspy.core.modules import (
            BaseModule,
            Atomizer,
            Planner,
            Executor,
            Aggregator,
            Verifier,
        )

        assert all([BaseModule, Atomizer, Planner, Executor, Aggregator, Verifier])

    def test_types_imports(self):
        """Should be able to import type definitions."""
        from roma_dspy.types import (
            TaskStatus,
            AgentType,
            TaskType,
            NodeType,
            PredictionStrategy,
        )

        assert all([TaskStatus, AgentType, TaskType, NodeType, PredictionStrategy])

    def test_config_imports(self):
        """Should be able to import config system."""
        from roma_dspy.config import ConfigManager
        from roma_dspy.config.schemas.root import ROMAConfig

        assert ConfigManager is not None
        assert ROMAConfig is not None


class TestSDKBasicUsage:
    """Test basic SDK usage patterns."""

    def test_create_recursive_solver(self):
        """Should be able to create RecursiveSolver."""
        from roma_dspy.core.engine.solve import RecursiveSolver
        from roma_dspy.core.registry import AgentRegistry

        # RecursiveSolver requires registry or config
        registry = AgentRegistry()
        solver = RecursiveSolver(max_depth=2, registry=registry)
        assert solver is not None
        assert solver.max_depth == 2

    def test_create_task_dag(self):
        """Should be able to create and use TaskDAG."""
        from roma_dspy.core.engine import TaskDAG
        from roma_dspy.core.signatures import TaskNode

        dag = TaskDAG()
        assert dag is not None

        # Add a node
        task = TaskNode(goal="Test task", depth=0, max_depth=2, execution_id="test_123")
        dag.add_node(task)

        assert len(dag.get_all_tasks()) == 1
        assert task.task_id in dag.graph

    def test_load_config(self):
        """Should be able to load configuration."""
        from roma_dspy.config.manager import ConfigManager

        try:
            mgr = ConfigManager()
            config = mgr.load_profile(profile="general")
            assert config is not None
            assert config.agents is not None
        except (FileNotFoundError, AttributeError) as e:
            pytest.skip(f"Config not available: {e}")

    def test_create_default_config(self):
        """Should be able to create default config."""
        from roma_dspy.config.schemas.root import ROMAConfig

        config = ROMAConfig()
        assert config is not None
        assert config.runtime is not None
        assert config.storage is not None


class TestSDKModuleCreation:
    """Test creating modules programmatically."""

    def test_create_executor(self):
        """Should be able to create Executor module."""
        from roma_dspy.core.modules import Executor
        from roma_dspy.types import PredictionStrategy
        import dspy

        class TestSignature(dspy.Signature):
            """Test signature"""

            input: str = dspy.InputField()
            output: str = dspy.OutputField()

        try:
            executor = Executor(
                signature=TestSignature,
                prediction_strategy=PredictionStrategy.CHAIN_OF_THOUGHT,
            )
            assert executor is not None
        except Exception as e:
            # Might fail without LLM config - that's okay
            error_msg = str(e).lower()
            # Should NOT fail due to missing optional deps
            assert "sqlalchemy" not in error_msg
            assert "mlflow" not in error_msg
            assert "boto3" not in error_msg

    def test_create_planner(self):
        """Should be able to create Planner module."""
        from roma_dspy.core.modules import Planner
        from roma_dspy.types import PredictionStrategy

        try:
            planner = Planner(prediction_strategy=PredictionStrategy.CHAIN_OF_THOUGHT)
            assert planner is not None
        except Exception as e:
            error_msg = str(e).lower()
            assert "sqlalchemy" not in error_msg
            assert "mlflow" not in error_msg


class TestSDKFileStorage:
    """Test FileStorage SDK usage."""

    def test_create_file_storage(self):
        """Should be able to create FileStorage."""
        from roma_dspy.core.storage import FileStorage
        from roma_dspy.config.schemas.storage import StorageConfig

        config = StorageConfig(base_path="/tmp/test_roma")
        storage = FileStorage(config=config, execution_id="test_exec_456")

        assert storage is not None
        assert storage.execution_id == "test_exec_456"
        assert storage.base_path == Path("/tmp/test_roma")

    def test_file_storage_paths(self):
        """FileStorage should provide correct paths."""
        from roma_dspy.core.storage import FileStorage
        from roma_dspy.config.schemas.storage import StorageConfig

        config = StorageConfig(base_path="/tmp/test_roma")
        storage = FileStorage(config=config, execution_id="exec_789")

        # Get various paths
        artifacts_path = storage.get_artifacts_path("test.txt")
        temp_path = storage.get_temp_path("temp.txt")

        assert artifacts_path is not None
        assert temp_path is not None
        assert "exec_789" in str(artifacts_path)


class TestSDKWithConfig:
    """Test SDK usage with configuration."""

    def test_solver_with_config(self):
        """Should be able to create solver with config."""
        from roma_dspy.core.engine.solve import RecursiveSolver
        from roma_dspy.config.manager import ConfigManager

        try:
            mgr = ConfigManager()
            config = mgr.load_profile(profile="general")
            solver = RecursiveSolver(max_depth=2, config=config)
            assert solver is not None
            assert solver.config is not None
        except (FileNotFoundError, AttributeError) as e:
            pytest.skip(f"Config not available: {e}")

    def test_module_with_config(self):
        """Should be able to create module with config."""
        from roma_dspy.core.modules import Executor
        from roma_dspy.config import ConfigManager

        try:
            root_config = ConfigManager.load(profile="general")
            executor_config = root_config.agents.executor

            executor = Executor(config=executor_config)
            assert executor is not None
        except (FileNotFoundError, AttributeError):
            pytest.skip("Config not available")


class TestSDKUtilities:
    """Test SDK utility functions."""

    def test_lazy_imports_available(self):
        """Lazy import utilities should be available."""
        from roma_dspy.utils.lazy_imports import (
            is_available,
            get_available_features,
            HAS_PERSISTENCE,
            HAS_MLFLOW,
        )

        assert callable(is_available)
        assert callable(get_available_features)
        assert isinstance(HAS_PERSISTENCE, bool)
        assert isinstance(HAS_MLFLOW, bool)

    def test_check_feature_availability(self):
        """Should be able to check feature availability."""
        from roma_dspy.utils.lazy_imports import get_available_features

        features = get_available_features()
        assert isinstance(features, dict)
        assert "persistence" in features
        assert "observability" in features
        assert "s3" in features


class TestSDKErrorHandling:
    """Test SDK error handling and messages."""

    def test_helpful_import_errors(self):
        """Missing optional deps should give helpful errors."""
        from roma_dspy.utils.lazy_imports import require_module

        with pytest.raises(ImportError) as exc_info:
            require_module("fake_module_xyz", "Test feature", "test_extra")

        error_msg = str(exc_info.value)
        assert "uv pip install" in error_msg
        assert "roma-dspy[test_extra]" in error_msg
        assert "pip install" in error_msg


class TestSDKTypeSafety:
    """Test type safety and validation."""

    def test_enum_types_available(self):
        """Enum types should be properly defined."""
        from roma_dspy.types import TaskStatus, AgentType, TaskType, PredictionStrategy

        # Should have enum values
        assert hasattr(TaskStatus, "PENDING")
        assert hasattr(TaskStatus, "COMPLETED")

        assert hasattr(AgentType, "EXECUTOR")
        assert hasattr(AgentType, "PLANNER")

        assert hasattr(TaskType, "RETRIEVE")
        assert hasattr(TaskType, "THINK")

        assert hasattr(PredictionStrategy, "CHAIN_OF_THOUGHT")
        assert hasattr(PredictionStrategy, "REACT")

    def test_pydantic_models_validate(self):
        """Pydantic models should validate correctly."""
        from roma_dspy.config.schemas.storage import StorageConfig

        # Valid config
        config = StorageConfig(base_path="/tmp/test")
        assert config.base_path == "/tmp/test"

        # Invalid config should raise validation error
        with pytest.raises(Exception):  # Pydantic validation error
            StorageConfig(base_path=None)


class TestSDKBackwardCompatibility:
    """Test that common SDK patterns still work."""

    def test_can_import_solve_function(self):
        """solve() function should be importable."""
        from roma_dspy import solve

        assert callable(solve)

    def test_can_import_recursive_solver(self):
        """RecursiveSolver should be importable."""
        from roma_dspy.core.engine.solve import RecursiveSolver

        assert RecursiveSolver is not None

    def test_can_create_modules(self):
        """Should be able to create all module types."""
        from roma_dspy.core.modules import (
            Atomizer,
            Planner,
            Executor,
            Aggregator,
            Verifier,
        )

        # All should be classes
        assert isinstance(Atomizer, type)
        assert isinstance(Planner, type)
        assert isinstance(Executor, type)
        assert isinstance(Aggregator, type)
        assert isinstance(Verifier, type)


# Mark all as integration tests
pytestmark = pytest.mark.integration


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
