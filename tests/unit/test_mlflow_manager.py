"""Tests for MLflow manager."""
import builtins
import pytest
from src.roma_dspy.config.schemas.observability import MLflowConfig
from src.roma_dspy.core.observability import MLflowManager
_real_import = builtins.__import__

def test_mlflow_config_defaults():
    """Test MLflow config defaults."""
    config = MLflowConfig()

    assert config.enabled is False  # Disabled by default
    assert config.tracking_uri == "http://127.0.0.1:5000"
    assert config.experiment_name == "ROMA-DSPy"
    assert config.log_traces is True
    assert config.log_traces_from_compile is False  # Expensive, off by default
    assert config.log_compiles is True
    assert config.log_evals is True


def test_mlflow_config_validation():
    """Test MLflow config validation."""
    with pytest.raises(ValueError, match="tracking_uri cannot be empty"):
        MLflowConfig(tracking_uri="")

    with pytest.raises(ValueError, match="experiment_name cannot be empty"):
        MLflowConfig(experiment_name="")


def test_mlflow_manager_disabled():
    """Test MLflow manager when disabled."""
    config = MLflowConfig(enabled=False)
    manager = MLflowManager(config)

    manager.initialize()

    assert not manager._initialized
    assert manager._mlflow is None


def test_mlflow_manager_enabled_no_mlflow_package(monkeypatch):
    """Test MLflow manager when package not installed."""
    config = MLflowConfig(enabled=True)
    manager = MLflowManager(config)

    # Mock import error
    def mock_import(name, *args, **kwargs):
        if name == "mlflow":
            # Giữ logic cũ: giả vờ mlflow không cài
            raise ImportError("mlflow not installed")
        # Dùng bản backup từ builtins thay vì __builtins__
        return _real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", mock_import)

    manager.initialize()

    # Should disable itself when mlflow not available
    assert not manager.config.enabled
    assert not manager._initialized


def test_mlflow_manager_trace_execution_disabled():
    """Test trace_execution context when disabled."""
    config = MLflowConfig(enabled=False)
    manager = MLflowManager(config)

    # Should be a no-op
    with manager.trace_execution("test_exec", {"key": "value"}) as run:
        assert run is None


def test_mlflow_manager_log_metrics_disabled():
    """Test log_metrics when disabled."""
    config = MLflowConfig(enabled=False)
    manager = MLflowManager(config)

    # Should be a no-op (no exception)
    manager.log_metrics({"accuracy": 0.95})
    manager.log_param("test", "value")
    manager.log_artifact("/tmp/test.txt")


@pytest.mark.skipif(True, reason="Requires mlflow package installed")
def test_mlflow_manager_integration():
    """Integration test with actual MLflow (skip if not installed)."""
    config = MLflowConfig(
        enabled=True,
        tracking_uri="sqlite:///test_mlflow.db",
        experiment_name="test_experiment"
    )
    manager = MLflowManager(config)

    manager.initialize()

    assert manager._initialized
    assert manager._mlflow is not None

    with manager.trace_execution("test_run", {"param1": "value1"}):
        manager.log_metrics({"metric1": 1.0})

    manager.shutdown()
