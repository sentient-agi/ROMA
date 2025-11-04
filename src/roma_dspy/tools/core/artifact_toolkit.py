"""
Minimal artifact management toolkit for ROMA-DSPy agents.

Provides only ONE essential tool: register_artifact.
Designed to minimize LLM overhead by keeping the tool count absolute minimum.

Why only one tool?
- Artifacts are automatically injected into context for dependent tasks
- No need for list_artifacts - agents see artifacts in their context
- Agent just needs ability to explicitly declare "this file is an artifact"

Tool:
- register_artifact: Explicitly register a file as an artifact
"""

import json
from pathlib import Path
from typing import List, Union

from loguru import logger

from roma_dspy.core.artifacts import ArtifactBuilder
from roma_dspy.core.context import ExecutionContext
from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.types import Artifact, ArtifactRegistrationRequest, ArtifactType


class ArtifactToolkit(BaseToolkit):
    """
    Minimal toolkit for artifact management.

    Only 1 essential tool to minimize LLM token overhead:
    - register_artifact: Explicit artifact registration

    Artifacts are automatically injected into dependent task contexts,
    so no list/query tools are needed.
    """

    REQUIRES_FILE_STORAGE: bool = True
    TOOLKIT_TYPE: str = "builtin"

    def _setup_dependencies(self) -> None:
        """Validate dependencies (none required)."""
        pass

    def _initialize_tools(self) -> None:
        """Initialize artifact storage directory."""
        if not self._file_storage:
            raise ValueError("ArtifactToolkit requires FileStorage")

        # Create artifacts subdirectory in execution storage
        self.artifacts_dir = Path(self._file_storage.root) / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Get artifact builder for metadata enrichment
        self.artifact_builder = ArtifactBuilder()

        logger.debug(
            "Initialized ArtifactToolkit",
            artifacts_dir=str(self.artifacts_dir)
        )

    async def register_artifact(
        self,
        artifacts: Union[ArtifactRegistrationRequest, List[ArtifactRegistrationRequest]],
    ) -> str:
        """
        Register one or more files as artifacts with metadata.

        Use this tool when you create file(s) that should be tracked as output artifacts.
        Supports both single artifact and batch registration for efficiency.

        Args:
            artifacts: Single ArtifactRegistrationRequest or list of requests.
                      Each request must include:
                      - file_path: Absolute path to the file
                      - name: Human-readable name
                      - artifact_type: Type (data_fetch, data_processed, data_analysis,
                                      report, plot, code, image, document)
                      - description: What the artifact contains
                      - derived_from: (optional) Comma-separated artifact IDs

        Returns:
            JSON string with success status and artifact details

        Examples:
            # Single artifact
            register_artifact(
                artifacts=ArtifactRegistrationRequest(
                    file_path="/tmp/analysis.csv",
                    name="crypto_analysis",
                    artifact_type="data_analysis",
                    description="Bitcoin price analysis results"
                )
            )

            # Multiple artifacts (batch)
            register_artifact(
                artifacts=[
                    ArtifactRegistrationRequest(
                        file_path="/tmp/chart.png",
                        name="price_chart",
                        artifact_type="plot",
                        description="BTC price chart"
                    ),
                    ArtifactRegistrationRequest(
                        file_path="/tmp/report.md",
                        name="analysis_report",
                        artifact_type="report",
                        description="Analysis summary"
                    )
                ]
            )
        """
        try:
            # Normalize input to list of Pydantic models
            if isinstance(artifacts, ArtifactRegistrationRequest):
                # Single Pydantic model
                requests_list = [artifacts]
            elif isinstance(artifacts, list):
                # Validate all items are ArtifactRegistrationRequest
                requests_list = []
                for idx, item in enumerate(artifacts):
                    if not isinstance(item, ArtifactRegistrationRequest):
                        return json.dumps({
                            "success": False,
                            "error": f"Invalid item at index {idx}: expected ArtifactRegistrationRequest, got {type(item).__name__}"
                        })
                    requests_list.append(item)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Invalid artifacts type: {type(artifacts).__name__}. Expected ArtifactRegistrationRequest or List[ArtifactRegistrationRequest]."
                })

            # Get ExecutionContext
            ctx = ExecutionContext.get()
            if not ctx:
                return json.dumps({
                    "success": False,
                    "error": "No execution context available"
                })

            # Get artifact registry
            registry = ctx.artifact_registry
            if not registry:
                return json.dumps({
                    "success": False,
                    "error": "No artifact registry available"
                })

            # Process all requests and build artifacts
            built_artifacts: List[Artifact] = []
            errors = []

            for idx, request in enumerate(requests_list):
                try:
                    # Validate file exists
                    file_path_obj = Path(request.file_path)
                    if not file_path_obj.exists():
                        errors.append({
                            "index": idx,
                            "name": request.name,
                            "error": f"File not found: {request.file_path}"
                        })
                        continue

                    # Validate and convert artifact type
                    try:
                        artifact_type_enum = ArtifactType.from_string(request.artifact_type)
                    except ValueError as e:
                        errors.append({
                            "index": idx,
                            "name": request.name,
                            "error": f"Invalid artifact type: {str(e)}"
                        })
                        continue

                    # Parse lineage if provided
                    parent_ids = []
                    if request.derived_from:
                        try:
                            from uuid import UUID
                            parent_ids = [UUID(id.strip()) for id in request.derived_from.split(",")]
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse derived_from IDs for {request.name}: {e}",
                                request_name=request.name
                            )

                    # Build artifact with enriched metadata
                    artifact = await self.artifact_builder.build(
                        name=request.name,
                        artifact_type=artifact_type_enum,
                        storage_path=str(file_path_obj.resolve()),
                        created_by_task=ctx.execution_id,
                        created_by_module="ArtifactToolkit",
                        description=request.description,
                        derived_from=parent_ids,
                    )

                    built_artifacts.append(artifact)

                except Exception as e:
                    errors.append({
                        "index": idx,
                        "name": request.name,
                        "error": f"Failed to build artifact: {str(e)}"
                    })

            # Handle empty results
            if not built_artifacts:
                # Empty input list is valid
                if not requests_list:
                    return json.dumps({
                        "success": True,
                        "count": 0,
                        "artifacts": []
                    })
                # All requests failed
                else:
                    return json.dumps({
                        "success": False,
                        "error": "All artifact registrations failed",
                        "details": errors
                    })

            # Register artifacts (single or batch)
            if len(built_artifacts) == 1:
                registered = [await registry.register(built_artifacts[0])]
            else:
                # Use batch registration for multiple artifacts
                registered = await registry.register_batch(built_artifacts)

            # Build response
            if len(registered) == 1:
                # Single artifact response (backward compatible)
                summary = registered[0].model_dump_summary()
                response = {
                    "success": True,
                    **summary,
                }
                if errors:
                    response["warnings"] = errors
                return json.dumps(response)
            else:
                # Multiple artifacts response
                summaries = [art.model_dump_summary() for art in registered]
                response = {
                    "success": True,
                    "count": len(registered),
                    "artifacts": summaries,
                }
                if errors:
                    response["warnings"] = errors
                return json.dumps(response)

        except Exception as e:
            logger.error(f"Failed to register artifact(s): {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": f"Failed to register artifact(s): {str(e)}"
            })
