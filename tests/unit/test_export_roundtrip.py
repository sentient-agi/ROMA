"""Round-trip tests for TUI v2 export/import utilities."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from roma_dspy.tui.models import ExecutionViewModel, MetricsSummary, TaskViewModel, TraceViewModel, DataSource
from roma_dspy.tui.types.export import ExportLevel
from roma_dspy.tui.utils.export import ExportService
from roma_dspy.tui.utils.import_service import ImportService


def _build_sample_execution() -> ExecutionViewModel:
    trace = TraceViewModel(
        trace_id="trace-1",
        task_id="task-1",
        parent_trace_id=None,
        name="executor",
        module="executor",
        duration=1.234,
        tokens=42,
        cost=0.0,
        inputs={"prompt": "hello"},
        outputs={"result": "world"},
        reasoning="chain",
        tool_calls=[],
        start_time="2025-01-01T00:00:00Z",
        start_ts=1735689600.0,
        model="test-model",
        source=DataSource.MLFLOW,
        has_full_io=True,
    )

    task = TaskViewModel(
        task_id="task-1",
        parent_task_id="root",
        goal="Test task",
        status="completed",
        module="executor",
        traces=[trace],
        subtask_ids=[],
        total_duration=1.234,
        total_tokens=42,
        total_cost=0.0,
    )

    return ExecutionViewModel(
        execution_id="exec-1",
        root_goal="Test root goal",
        status="completed",
        tasks={task.task_id: task},
        root_task_ids=[task.task_id],
        checkpoints=[],
        metrics=MetricsSummary(total_calls=1, total_tokens=42, total_cost=0.0, total_duration=1.234),
        data_sources={"mlflow": True},
        warnings=[],
    )


def test_export_import_roundtrip(tmp_path: Path) -> None:
    """Exported executions should import back to equivalent view models."""

    execution = _build_sample_execution()
    export_file = tmp_path / "execution.json"

    ExportService.export_execution_full(
        execution=execution,
        filepath=export_file,
        level=ExportLevel.FULL,
        exclude_io=False,
        redact_sensitive=False,
        api_url="http://example.com",
    )

    imported = ImportService().load_from_file(export_file, validate_checksum=True)

    # Ensure parent id normalization happened
    assert imported.tasks["task-1"].parent_task_id is None

    # Make comparison fair by normalising root parent on original
    execution.tasks["task-1"].parent_task_id = None

    assert asdict(execution) == asdict(imported)
