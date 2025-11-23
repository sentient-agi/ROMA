"""
Test that minimal installation works without optional dependencies.

These tests verify that ROMA-DSPy core functionality works without
infrastructure dependencies (PostgreSQL, MLflow, boto3, E2B).

Run in clean environment:
    python -m venv test_venv
    source test_venv/bin/activate  # or test_venv\Scripts\activate on Windows
    pip install -e .  # Minimal install - NO extras
    pytest tests/test_minimal_install.py -v

Or with uv (recommended):
    uv venv
    source .venv/bin/activate
    uv pip install -e .
    uv run pytest tests/test_minimal_install.py -v
"""

import sys
import pytest


class TestMinimalImports:
    """Test that core modules import without optional dependencies."""

    def test_core_engine_imports(self):
        """Core engine modules should import successfully."""
        from roma_dspy.core.engine import TaskDAG
        from roma_dspy.core.engine.solve import RecursiveSolver, solve
        from roma_dspy.core.engine.runtime import ModuleRuntime

        assert TaskDAG is not None
        assert RecursiveSolver is not None
        assert solve is not None
        assert ModuleRuntime is not None

    def test_core_module_imports(self):
        """Core module types should import successfully."""
        from roma_dspy.core.modules import (
            BaseModule,
            Atomizer,
            Planner,
            Executor,
            Aggregator,
            Verifier,
        )

        assert BaseModule is not None
        assert Atomizer is not None
        assert Planner is not None
        assert Executor is not None
        assert Aggregator is not None
        assert Verifier is not None

    def test_type_imports(self):
        """Type definitions should import successfully."""
        from roma_dspy.types import (
            TaskStatus,
            AgentType,
            TaskType,
            NodeType,
            PredictionStrategy,
        )

        assert TaskStatus is not None
        assert AgentType is not None
        assert TaskType is not None
        assert NodeType is not None
        assert PredictionStrategy is not None

    def test_lazy_imports_module(self):
        """Lazy imports utility should be available."""
        from roma_dspy.utils.lazy_imports import (
            is_available,
            require_module,
            get_available_features,
            HAS_PERSISTENCE,
            HAS_MLFLOW,
            HAS_S3,
            HAS_CODE_EXECUTION,
        )

        assert is_available is not None
        assert require_module is not None
        assert get_available_features is not None
        # Flags should be defined (True or False)
        assert isinstance(HAS_PERSISTENCE, bool)
        assert isinstance(HAS_MLFLOW, bool)
        assert isinstance(HAS_S3, bool)
        assert isinstance(HAS_CODE_EXECUTION, bool)


class TestOptionalDependenciesNotRequired:
    """Test that optional dependencies are truly optional."""

    def test_no_postgres_in_modules(self):
        """PostgreSQL modules should not be imported at top level."""
        import sys

        # Get baseline of modules before importing core
        baseline = set(sys.modules.keys())

        # Import core modules - should not trigger postgres imports
        from roma_dspy.core.engine.solve import RecursiveSolver
        from roma_dspy.core.modules import Executor

        # Get new modules that were loaded
        new_modules = set(sys.modules.keys()) - baseline

        # Check that postgres modules are NOT in the newly loaded modules
        postgres_modules = {"sqlalchemy", "asyncpg", "alembic", "psycopg2"}
        imported_postgres = new_modules & postgres_modules

        assert (
            len(imported_postgres) == 0
        ), f"PostgreSQL modules should not be auto-imported. Found: {imported_postgres}"

    def test_no_mlflow_in_modules(self):
        """MLflow should not be imported at top level."""
        import sys

        # Get baseline of modules before importing core
        baseline = set(sys.modules.keys())

        # Import core modules - should not trigger mlflow imports
        from roma_dspy.core.engine.solve import RecursiveSolver

        # Get new modules that were loaded
        new_modules = set(sys.modules.keys()) - baseline

        # Check that mlflow is NOT in the newly loaded modules
        mlflow_modules = {"mlflow"}
        imported_mlflow = new_modules & mlflow_modules

        assert (
            len(imported_mlflow) == 0
        ), f"MLflow should not be auto-imported. Found: {imported_mlflow}"

    def test_no_boto3_in_modules(self):
        """boto3 should not be imported at top level."""
        import sys

        # Get baseline of modules before importing core
        baseline = set(sys.modules.keys())

        # Import FileStorage - should not trigger boto3 imports
        from roma_dspy.core.storage import FileStorage

        # Get new modules that were loaded
        new_modules = set(sys.modules.keys()) - baseline

        # Check that boto3 is NOT in the newly loaded modules
        boto3_modules = {"boto3", "botocore"}
        imported_boto3 = new_modules & boto3_modules

        assert (
            len(imported_boto3) == 0
        ), f"boto3 should not be auto-imported. Found: {imported_boto3}"

    def test_no_e2b_in_modules(self):
        """E2B should not be imported at top level."""
        import sys

        # Get baseline of modules before importing core
        baseline = set(sys.modules.keys())

        # Import core modules - should not trigger E2B imports
        from roma_dspy.core.modules import Executor

        # Get new modules that were loaded
        new_modules = set(sys.modules.keys()) - baseline

        # Check that E2B is NOT in the newly loaded modules
        e2b_modules = {"e2b", "e2b_code_interpreter"}
        imported_e2b = new_modules & e2b_modules

        assert (
            len(imported_e2b) == 0
        ), f"E2B should not be auto-imported. Found: {imported_e2b}"


class TestLazyImportUtilities:
    """Test lazy import utility functions."""

    def test_is_available_for_core_modules(self):
        """is_available should work for checking any module."""
        from roma_dspy.utils.lazy_imports import is_available

        # Core Python module - always available
        assert is_available("sys") is True
        assert is_available("os") is True

        # Fake module - should be False
        assert is_available("nonexistent_module_xyz123") is False

    def test_get_available_features(self):
        """get_available_features should return dict of feature availability."""
        from roma_dspy.utils.lazy_imports import get_available_features

        features = get_available_features()

        assert isinstance(features, dict)
        assert "persistence" in features
        assert "observability" in features
        assert "s3" in features
        assert "code_execution" in features

        # All values should be booleans
        for feature, available in features.items():
            assert isinstance(available, bool), f"{feature} availability should be bool"

    def test_require_module_raises_helpful_error(self):
        """require_module should raise ImportError with install instructions."""
        from roma_dspy.utils.lazy_imports import require_module

        with pytest.raises(ImportError) as exc_info:
            require_module("nonexistent_module", "Test feature", "test_extra")

        error_msg = str(exc_info.value)
        # Should mention uv (recommended)
        assert "uv pip install" in error_msg
        # Should mention the extra name
        assert "roma-dspy[test_extra]" in error_msg
        # Should also show pip alternative
        assert "pip install" in error_msg


class TestConfigLoading:
    """Test that configuration system works without optional deps."""

    def test_config_import(self):
        """Config schemas should import successfully."""
        from roma_dspy.config.schemas.root import ROMAConfig
        from roma_dspy.config.schemas.base import CacheConfig
        from roma_dspy.config.schemas.storage import StorageConfig

        assert ROMAConfig is not None
        assert CacheConfig is not None
        assert StorageConfig is not None

    def test_default_config_creation(self):
        """Should be able to create default config without optional deps."""
        from roma_dspy.config.schemas.root import ROMAConfig

        # Create default config
        config = ROMAConfig()

        assert config is not None
        assert config.runtime is not None
        assert config.storage is not None


class TestFileStorageWithoutS3:
    """Test FileStorage works without boto3/S3."""

    def test_file_storage_import(self):
        """FileStorage should import without S3 dependencies."""
        from roma_dspy.core.storage import FileStorage

        assert FileStorage is not None

    def test_file_storage_creation(self):
        """Should be able to create FileStorage without S3."""
        from roma_dspy.core.storage import FileStorage
        from roma_dspy.config.schemas.storage import StorageConfig

        config = StorageConfig(base_path="/tmp/test")
        storage = FileStorage(config=config, execution_id="test_exec_123")

        assert storage is not None
        assert storage.execution_id == "test_exec_123"


class TestErrorMessages:
    """Test that error messages are helpful and mention uv."""

    def test_e2b_import_error_message(self):
        """E2B toolkit should have helpful error if not installed."""
        try:
            from roma_dspy.tools.core.e2b import E2BToolkit

            # Try to create toolkit - will fail if e2b not installed
            toolkit = E2BToolkit(toolkit_config={})
        except ImportError as e:
            error_msg = str(e)
            # Should mention uv
            assert "uv pip install" in error_msg
            # Should mention the extra
            assert "roma-dspy[e2b]" in error_msg
            # Should also mention pip alternative
            assert "pip install" in error_msg
        except Exception:
            # Other errors are fine (like missing API key)
            pass


@pytest.mark.skipif("pytest" not in sys.modules, reason="Requires pytest")
class TestMinimalFunctionality:
    """Test basic functionality works without optional deps.

    Note: These tests use mocked LLMs to avoid requiring API keys.
    """

    def test_task_dag_creation(self):
        """Should be able to create and manipulate TaskDAG."""
        from roma_dspy.core.engine import TaskDAG
        from roma_dspy.core.signatures import TaskNode

        dag = TaskDAG()
        assert dag is not None

        # TaskNode requires execution_id
        task = TaskNode(
            goal="Test task", depth=0, max_depth=2, execution_id="test_exec_123"
        )
        dag.add_node(task)

        assert task.task_id in dag.graph
        assert len(dag.get_all_tasks()) == 1

    def test_module_creation_without_llm(self):
        """Should be able to create modules (though they won't execute without LLM)."""
        from roma_dspy.core.modules import Executor
        from roma_dspy.types import PredictionStrategy
        import dspy

        # Create a simple signature for testing
        class SimpleSignature(dspy.Signature):
            """Test signature"""

            input_text: str = dspy.InputField()
            output_text: str = dspy.OutputField()

        # Create executor without LLM (will fail on execution, but should construct)
        try:
            executor = Executor(
                signature=SimpleSignature, prediction_strategy=PredictionStrategy.REACT
            )
            # If we get here, construction worked
            assert executor is not None
        except Exception as e:
            # If it fails, it should be about missing LLM config, not dependencies
            error_msg = str(e).lower()
            # Should NOT be about missing postgres/mlflow/etc
            assert "sqlalchemy" not in error_msg
            assert "mlflow" not in error_msg
            assert "boto3" not in error_msg


# Mark all tests as unit tests
pytestmark = pytest.mark.unit


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v", "--tb=short"])
