"""
Unit tests for Artifact Context Injection (Phase 4).

Tests cover:
- ArtifactInjectionMode enum
- Context models with artifact references
- ArtifactQueryService
- ContextManager async artifact querying
- Config system integration
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from roma_dspy.types.artifact_injection import ArtifactInjectionMode
from roma_dspy.types.artifact_models import ArtifactReference
from roma_dspy.types.artifact_types import ArtifactType
from roma_dspy.core.context.models import (
    ExecutorSpecificContext,
    PlannerSpecificContext,
    AggregatorSpecificContext,
    DependencyResult,
)
from roma_dspy.core.artifacts.query_service import ArtifactQueryService
from roma_dspy.core.artifacts.artifact_registry import ArtifactRegistry
from roma_dspy.types import Artifact, ArtifactMetadata, MediaType
from roma_dspy.config.schemas.agents import AgentConfig


class TestArtifactInjectionMode:
    """Test ArtifactInjectionMode enum."""

    def test_enum_values(self):
        """Test all enum values exist."""
        assert ArtifactInjectionMode.NONE.value == "none"
        assert ArtifactInjectionMode.DEPENDENCIES.value == "dependencies"
        assert ArtifactInjectionMode.SUBTASK.value == "subtask"
        assert ArtifactInjectionMode.FULL.value == "full"

    def test_from_string_valid(self):
        """Test from_string with valid values."""
        assert ArtifactInjectionMode.from_string("none") == ArtifactInjectionMode.NONE
        assert ArtifactInjectionMode.from_string("dependencies") == ArtifactInjectionMode.DEPENDENCIES
        assert ArtifactInjectionMode.from_string("subtask") == ArtifactInjectionMode.SUBTASK
        assert ArtifactInjectionMode.from_string("full") == ArtifactInjectionMode.FULL

    def test_from_string_case_insensitive(self):
        """Test from_string is case-insensitive."""
        assert ArtifactInjectionMode.from_string("NONE") == ArtifactInjectionMode.NONE
        assert ArtifactInjectionMode.from_string("Dependencies") == ArtifactInjectionMode.DEPENDENCIES
        assert ArtifactInjectionMode.from_string("FULL") == ArtifactInjectionMode.FULL

    def test_from_string_invalid(self):
        """Test from_string raises ValueError for invalid input."""
        with pytest.raises(ValueError, match="Invalid artifact injection mode"):
            ArtifactInjectionMode.from_string("invalid")

    def test_str_enum_inheritance(self):
        """Test enum inherits from str for DSPy compatibility."""
        mode = ArtifactInjectionMode.DEPENDENCIES
        assert isinstance(mode, str)
        assert mode == "dependencies"


class TestContextModelsWithArtifacts:
    """Test context models with artifact references."""

    def test_executor_specific_context_empty_artifacts(self):
        """Test ExecutorSpecificContext with no artifacts."""
        ctx = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=[]
        )
        assert ctx.available_artifacts == []
        # Check that XML contains either empty tag or "No" message
        xml = ctx.to_xml()
        assert "No dependencies or artifacts" in xml or "<available_artifacts" in xml

    def test_executor_specific_context_with_artifacts(self):
        """Test ExecutorSpecificContext with artifact references."""
        artifact_ref = ArtifactReference(
            artifact_id=uuid4(),
            created_by_task="task-123",
            artifact_type=ArtifactType.DATA_PROCESSED,
            name="price_data.csv",
            storage_path="/tmp/price_data.csv",
            description="Bitcoin price data"
        )
        ctx = ExecutorSpecificContext(
            dependency_results=[
                DependencyResult(goal="Fetch data", output="Data fetched successfully")
            ],
            available_artifacts=[artifact_ref]
        )
        assert len(ctx.available_artifacts) == 1
        assert ctx.available_artifacts[0].name == "price_data.csv"

        xml = ctx.to_xml()
        assert "available_artifacts" in xml
        assert "price_data.csv" in xml

    def test_planner_specific_context_with_artifacts(self):
        """Test PlannerSpecificContext with artifact references."""
        artifact_ref = ArtifactReference(
            artifact_id=uuid4(),
            created_by_task="parent-task",
            artifact_type=ArtifactType.REPORT,
            name="analysis.md",
            storage_path="/tmp/analysis.md",
            description="Market analysis report"
        )
        ctx = PlannerSpecificContext(
            parent_results=[],
            sibling_results=[],
            available_artifacts=[artifact_ref]
        )
        assert len(ctx.available_artifacts) == 1

        xml = ctx.to_xml()
        assert "available_artifacts" in xml
        assert "analysis.md" in xml

    def test_aggregator_specific_context_with_artifacts(self):
        """Test AggregatorSpecificContext with artifact references."""
        artifacts = [
            ArtifactReference(
                artifact_id=uuid4(),
                created_by_task="subtask-1",
                artifact_type=ArtifactType.DATA_PROCESSED,
                name="data.parquet",
                storage_path="/tmp/data.parquet",
                description="Processed data"
            ),
            ArtifactReference(
                artifact_id=uuid4(),
                created_by_task="subtask-2",
                artifact_type=ArtifactType.PLOT,
                name="chart.png",
                storage_path="/tmp/chart.png",
                description="Price chart"
            )
        ]
        ctx = AggregatorSpecificContext(available_artifacts=artifacts)
        assert len(ctx.available_artifacts) == 2

        xml = ctx.to_xml()
        assert "available_artifacts" in xml
        assert "data.parquet" in xml
        assert "chart.png" in xml

    def test_aggregator_specific_context_no_artifacts(self):
        """Test AggregatorSpecificContext with no artifacts."""
        ctx = AggregatorSpecificContext(available_artifacts=[])
        xml = ctx.to_xml()
        assert "No artifacts" in xml


class TestArtifactQueryService:
    """Test ArtifactQueryService for querying artifacts."""

    @pytest.fixture
    def query_service(self):
        """Create ArtifactQueryService instance."""
        return ArtifactQueryService()

    @pytest.fixture
    def mock_registry(self):
        """Create mock artifact registry."""
        registry = Mock(spec=ArtifactRegistry)
        return registry

    @pytest.mark.asyncio
    async def test_get_artifacts_none_mode(self, query_service, mock_registry):
        """Test NONE mode returns empty list."""
        result = await query_service.get_artifacts_for_dependencies(
            registry=mock_registry,
            dependency_task_ids=["task-1", "task-2"],
            mode=ArtifactInjectionMode.NONE
        )
        assert result == []
        mock_registry.get_by_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_artifacts_dependencies_mode(self, query_service, mock_registry):
        """Test DEPENDENCIES mode queries dependency tasks."""
        # Setup mock artifacts
        artifact1 = Artifact(
            artifact_id=uuid4(),
            name="data.csv",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/data.csv",
            created_by_task="task-1",
            created_by_module="executor",
            created_at="2025-01-01T00:00:00",
            metadata=ArtifactMetadata(description="Test data")
        )
        artifact2 = Artifact(
            artifact_id=uuid4(),
            name="chart.png",
            artifact_type=ArtifactType.PLOT,
            media_type=MediaType.IMAGE,
            storage_path="/tmp/chart.png",
            created_by_task="task-2",
            created_by_module="executor",
            created_at="2025-01-01T00:01:00",
            metadata=ArtifactMetadata(description="Test chart")
        )

        async def mock_get_by_task(task_id):
            if task_id == "task-1":
                return [artifact1]
            elif task_id == "task-2":
                return [artifact2]
            return []

        mock_registry.get_by_task = AsyncMock(side_effect=mock_get_by_task)

        result = await query_service.get_artifacts_for_dependencies(
            registry=mock_registry,
            dependency_task_ids=["task-1", "task-2"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert len(result) == 2
        assert all(isinstance(ref, ArtifactReference) for ref in result)
        # Order may be non-deterministic, so check names are in the set
        result_names = {ref.name for ref in result}
        assert result_names == {"data.csv", "chart.png"}

    @pytest.mark.asyncio
    async def test_get_all_artifacts(self, query_service, mock_registry):
        """Test FULL mode gets all artifacts."""
        artifacts = [
            Artifact(
                artifact_id=uuid4(),
                name=f"data-{i}.csv",
                artifact_type=ArtifactType.DATA_PROCESSED,
                media_type=MediaType.FILE,
                storage_path=f"/tmp/data-{i}.csv",
                created_by_task=f"task-{i}",
                created_by_module="executor",
                created_at="2025-01-01T00:00:00",
                metadata=ArtifactMetadata(description=f"Test data {i}")
            )
            for i in range(5)
        ]
        mock_registry.get_all = AsyncMock(return_value=artifacts)

        result = await query_service.get_all_artifacts(
            registry=mock_registry,
            mode=ArtifactInjectionMode.FULL
        )

        assert len(result) == 5
        assert all(isinstance(ref, ArtifactReference) for ref in result)
        mock_registry.get_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_artifacts_deduplication(self, query_service, mock_registry):
        """Test artifact deduplication by ID."""
        artifact_id = uuid4()
        duplicate_artifact = Artifact(
            artifact_id=artifact_id,  # Same ID
            name="data.csv",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/data.csv",
            created_by_task="task-1",
            created_by_module="executor",
            created_at="2025-01-01T00:00:00",
            metadata=ArtifactMetadata(description="Test data")
        )

        # Both tasks return the same artifact (should deduplicate)
        mock_registry.get_by_task = AsyncMock(return_value=[duplicate_artifact])

        result = await query_service.get_artifacts_for_dependencies(
            registry=mock_registry,
            dependency_task_ids=["task-1", "task-1"],  # Duplicate task IDs
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        # Should only return 1 artifact (deduplicated)
        assert len(result) == 1
        assert result[0].artifact_id == artifact_id


class TestAgentConfigArtifactInjection:
    """Test artifact injection mode in agent configuration."""

    def test_agent_config_default_injection_mode(self):
        """Test default artifact_injection_mode is 'full'."""
        config = AgentConfig()
        assert config.artifact_injection_mode == "full"

    def test_agent_config_custom_injection_mode(self):
        """Test setting custom injection mode."""
        config = AgentConfig(artifact_injection_mode="dependencies")
        assert config.artifact_injection_mode == "dependencies"

    def test_agent_config_validates_injection_mode(self):
        """Test validation of artifact_injection_mode."""
        # Valid modes should pass
        for mode in ["none", "dependencies", "subtask", "full"]:
            config = AgentConfig(artifact_injection_mode=mode)
            assert config.artifact_injection_mode == mode

    def test_agent_config_invalid_injection_mode(self):
        """Test invalid injection mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid artifact injection mode"):
            AgentConfig(artifact_injection_mode="invalid_mode")


class TestContextManagerArtifactQueries:
    """Test ContextManager artifact querying integration."""

    @pytest.mark.asyncio
    async def test_query_artifacts_for_context_none(self):
        """Test _query_artifacts_for_context with NONE mode."""
        from roma_dspy.core.context.manager import ContextManager
        from roma_dspy.core.storage import FileStorage

        file_storage = Mock(spec=FileStorage)
        file_storage.root = "/tmp/test"
        file_storage.execution_id = "exec-123"

        manager = ContextManager(file_storage, "test objective")

        result = await manager._query_artifacts_for_context(
            task_ids=["task-1", "task-2"],
            injection_mode=ArtifactInjectionMode.NONE,
            current_task_id="current-task"
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_query_artifacts_no_registry(self):
        """Test _query_artifacts_for_context when no registry available."""
        from roma_dspy.core.context.manager import ContextManager
        from roma_dspy.core.context import ExecutionContext
        from roma_dspy.core.storage import FileStorage

        file_storage = Mock(spec=FileStorage)
        file_storage.root = "/tmp/test"
        file_storage.execution_id = "exec-123"

        manager = ContextManager(file_storage, "test objective")

        # Mock ExecutionContext.get_artifact_registry to return None
        with patch.object(ExecutionContext, 'get_artifact_registry', return_value=None):
            result = await manager._query_artifacts_for_context(
                task_ids=["task-1"],
                injection_mode=ArtifactInjectionMode.DEPENDENCIES,
                current_task_id="current-task"
            )

        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])