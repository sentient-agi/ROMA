"""Regression test ensuring terminal_bench_subprocess_v2 config wires CodeAct + JSONAdapter."""

import os

import pytest
import dspy

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.modules.executor import Executor
from roma_dspy.types import PredictionStrategy


def _dummy_tool():
    return "ok"


def test_terminal_bench_subprocess_profile_uses_codeact_with_json_adapter(monkeypatch):
    monkeypatch.setenv("ROMA_PROFILE", "terminal_bench_subprocess_v2")
    config = ConfigManager().load_config(profile="terminal_bench_subprocess_v2")
    executor_config = config.agents.executor

    executor = Executor(config=executor_config)

    assert executor._lazy_init_needed is True
    assert executor._prediction_strategy == PredictionStrategy.CODE_ACT
    assert executor._predictor is None
    assert type(executor._adapter).__name__ == "JSONAdapter"

    executor._update_predictor_tools({"dummy": _dummy_tool})
    assert isinstance(executor._predictor, dspy.CodeAct)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
