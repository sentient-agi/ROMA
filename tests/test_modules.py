"""Integration-style tests for ROMA DSPy modules."""

from __future__ import annotations

import pytest

from roma_dspy import Aggregator, Atomizer, Executor, Planner, Verifier, SubTask
from roma_dspy.types import NodeType, TaskType


class DummyLM:
    """Minimal LM stub for dspy.context usage during tests."""

    def __init__(self, name: str = "stub/lm", *, cache: bool = False, **kwargs):
        self.model = name
        self.model_type = "stub"
        self.cache = cache
        self.kwargs = kwargs


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def dummy_lm() -> DummyLM:
    return DummyLM()


def test_atomizer_forward(dummy_lm: DummyLM) -> None:
    atomizer = Atomizer(lm=dummy_lm)
    result = atomizer.forward("Atomic: file receipts")

    assert result.is_atomic is True
    assert result.node_type == NodeType.EXECUTE


@pytest.mark.anyio("asyncio")
async def test_atomizer_aforward() -> None:
    atomizer = Atomizer(lm=DummyLM())
    result = await atomizer.aforward("Plan quarterly roadmap")

    assert result.is_atomic is False
    assert result.node_type == NodeType.PLAN


def test_planner_forward(dummy_lm: DummyLM) -> None:
    planner = Planner(lm=dummy_lm)
    result = planner.forward("Launch a marketing campaign")

    assert len(result.subtasks) == 2
    assert result.subtasks[0].task_type == TaskType.THINK
    assert result.dependencies_graph == {"step 2": ["step 1"]}


@pytest.mark.anyio("asyncio")
async def test_planner_aforward() -> None:
    planner = Planner(lm=DummyLM())
    result = await planner.aforward("Launch a marketing campaign")

    assert len(result.subtasks) == 2
    assert result.subtasks[1].task_type == TaskType.WRITE


def test_executor_forward(dummy_lm: DummyLM) -> None:
    executor = Executor(lm=dummy_lm)

    def tool(_: str) -> str:
        return "tool-response"

    result = executor.forward("Compile sprint report", tools=[tool])

    assert result.output == "executed:Compile sprint report"
    assert result.sources == ["stub-source"]


@pytest.mark.anyio("asyncio")
async def test_executor_aforward() -> None:
    executor = Executor(lm=DummyLM())
    result = await executor.aforward("Draft onboarding guide")

    assert result.output == "executed:Draft onboarding guide"


def _make_subtasks() -> list[SubTask]:
    return [
        SubTask(goal="Task A", task_type=TaskType.THINK, dependencies=[]),
        SubTask(goal="Task B", task_type=TaskType.WRITE, dependencies=["Task A"]),
    ]


def test_aggregator_forward(dummy_lm: DummyLM) -> None:
    aggregator = Aggregator(lm=dummy_lm)
    subtasks = _make_subtasks()
    result = aggregator.forward("Deliver project summary", subtasks)

    assert result.synthesized_result == "Task A | Task B"


@pytest.mark.anyio("asyncio")
async def test_aggregator_aforward() -> None:
    aggregator = Aggregator(lm=DummyLM())
    subtasks = _make_subtasks()
    result = await aggregator.aforward("Deliver project summary", subtasks)

    assert result.synthesized_result == "Task A | Task B"


def test_verifier_forward(dummy_lm: DummyLM) -> None:
    verifier = Verifier(lm=dummy_lm)
    verdict = verifier.forward("Deliver project summary", "All good")

    assert verdict.verdict is True
    assert verdict.feedback is None


@pytest.mark.anyio("asyncio")
async def test_verifier_aforward() -> None:
    verifier = Verifier(lm=DummyLM())
    verdict = await verifier.aforward("Deliver project summary", "Fail to comply")

    assert verdict.verdict is False
    assert verdict.feedback == "Output flagged by verifier"
