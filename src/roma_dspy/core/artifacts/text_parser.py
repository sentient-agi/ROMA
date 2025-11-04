"""
LLM output text parser for artifact declarations.

Parses LLM output text for explicit artifact declarations in multiple formats:
- Markdown: ## ARTIFACT: Name\n- path: ...\n- type: ...\n- description: ...
- JSON: {"artifacts": [{"path": "...", "type": "...", "description": "..."}]}
- XML: <artifact><path>...</path><type>...</type><description>...</description></artifact>

Detection Strategy:
- Parse all formats and merge results
- Validate file paths exist and are inside execution directory
- Infer artifact type if not specified
- Deduplication via registry.get_by_path()
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from roma_dspy.core.artifacts import ArtifactBuilder
from roma_dspy.core.context import ExecutionContext
from roma_dspy.types import ArtifactType


# Regex patterns for artifact declarations
MARKDOWN_ARTIFACT_PATTERN = re.compile(
    r'##\s*ARTIFACT:\s*(.+?)\n((?:[-*]\s*\w+:\s*.+\n?)+)',
    re.MULTILINE | re.IGNORECASE
)

MARKDOWN_FIELD_PATTERN = re.compile(
    r'[-*]\s*(\w+):\s*(.+)',
    re.MULTILINE
)


def parse_markdown_artifacts(text: str, execution_dir: Path) -> List[Dict[str, str]]:
    """
    Parse artifact declarations from Markdown format.

    Expected format:
        ## ARTIFACT: Name
        - path: /path/to/file
        - type: data_processed
        - description: Description here

    Args:
        text: Markdown text to parse
        execution_dir: Execution directory for path validation

    Returns:
        List of artifact declarations (path, type, description)
    """
    artifacts: List[Dict[str, str]] = []

    try:
        # Find all ARTIFACT sections
        matches = MARKDOWN_ARTIFACT_PATTERN.findall(text)

        for name, fields_block in matches:
            artifact_dict: Dict[str, str] = {"name": name.strip()}

            # Parse fields
            field_matches = MARKDOWN_FIELD_PATTERN.findall(fields_block)
            for key, value in field_matches:
                artifact_dict[key.lower().strip()] = value.strip()

            # Extract and validate
            declaration = extract_artifact_declaration(artifact_dict)
            if declaration and _validate_artifact_path(declaration, execution_dir):
                artifacts.append(declaration)

    except Exception as e:
        logger.debug(f"Failed to parse Markdown artifacts: {e}")

    logger.debug(f"Parsed {len(artifacts)} artifact(s) from Markdown")
    return artifacts


def parse_json_artifacts(text: str, execution_dir: Path) -> List[Dict[str, str]]:
    """
    Parse artifact declarations from JSON format.

    Expected format:
        {
            "artifacts": [
                {
                    "path": "/path/to/file",
                    "type": "data_processed",
                    "description": "Description"
                }
            ]
        }

    Args:
        text: JSON text to parse
        execution_dir: Execution directory for path validation

    Returns:
        List of artifact declarations
    """
    artifacts: List[Dict[str, str]] = []

    try:
        # Try to parse as JSON
        data = json.loads(text)

        # Look for artifacts array
        if isinstance(data, dict) and "artifacts" in data:
            artifact_list = data["artifacts"]
            if isinstance(artifact_list, list):
                for item in artifact_list:
                    if isinstance(item, dict):
                        declaration = extract_artifact_declaration(item)
                        if declaration and _validate_artifact_path(declaration, execution_dir):
                            artifacts.append(declaration)

    except json.JSONDecodeError as e:
        logger.debug(f"JSON parsing failed: {e}")
    except Exception as e:
        logger.debug(f"Failed to parse JSON artifacts: {e}")

    logger.debug(f"Parsed {len(artifacts)} artifact(s) from JSON")
    return artifacts


def parse_xml_artifacts(text: str, execution_dir: Path) -> List[Dict[str, str]]:
    """
    Parse artifact declarations from XML format.

    Expected format:
        <artifacts>
            <artifact>
                <path>/path/to/file</path>
                <type>data_processed</type>
                <description>Description</description>
            </artifact>
        </artifacts>

    Args:
        text: XML text to parse (may be embedded in other text)
        execution_dir: Execution directory for path validation

    Returns:
        List of artifact declarations
    """
    artifacts: List[Dict[str, str]] = []

    try:
        # Extract XML fragments from text (handle embedded XML)
        # Look for <artifacts>...</artifacts> blocks
        import re
        xml_pattern = re.compile(r'<artifacts>(.*?)</artifacts>', re.DOTALL)
        matches = xml_pattern.findall(text)

        if not matches:
            # Try parsing entire text as XML
            matches = [text]

        for xml_fragment in matches:
            try:
                # Wrap fragment if it doesn't have root element
                if not xml_fragment.strip().startswith('<artifacts>'):
                    xml_fragment = f'<artifacts>{xml_fragment}</artifacts>'

                root = ET.fromstring(xml_fragment)

                # Find all artifact elements
                for artifact_elem in root.findall('.//artifact'):
                    artifact_dict: Dict[str, str] = {}

                    # Extract fields
                    for child in artifact_elem:
                        if child.text:
                            artifact_dict[child.tag.lower()] = child.text.strip()

                    declaration = extract_artifact_declaration(artifact_dict)
                    if declaration and _validate_artifact_path(declaration, execution_dir):
                        artifacts.append(declaration)

            except ET.ParseError:
                # Skip malformed fragments
                continue

    except Exception as e:
        logger.debug(f"Failed to parse XML artifacts: {e}")

    logger.debug(f"Parsed {len(artifacts)} artifact(s) from XML")
    return artifacts


def parse_all_formats(text: str, execution_dir: Path) -> List[Dict[str, str]]:
    """
    Parse artifact declarations from all supported formats.

    Tries Markdown, JSON, and XML parsing and merges results with deduplication.

    Args:
        text: Text to parse (may contain mixed formats)
        execution_dir: Execution directory for path validation

    Returns:
        Deduplicated list of artifact declarations
    """
    all_artifacts: List[Dict[str, str]] = []

    # Parse all formats
    all_artifacts.extend(parse_markdown_artifacts(text, execution_dir))
    all_artifacts.extend(parse_json_artifacts(text, execution_dir))
    all_artifacts.extend(parse_xml_artifacts(text, execution_dir))

    # Deduplicate by path
    seen_paths: Set[str] = set()
    deduplicated: List[Dict[str, str]] = []

    for artifact in all_artifacts:
        path = artifact.get("path", "")
        if path and path not in seen_paths:
            seen_paths.add(path)
            deduplicated.append(artifact)

    logger.debug(
        f"Parsed {len(all_artifacts)} total, {len(deduplicated)} unique artifact(s)"
    )
    return deduplicated


def extract_artifact_declaration(data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Extract structured artifact info from raw declaration.

    Args:
        data: Raw artifact data (from MD/JSON/XML)

    Returns:
        Structured artifact dict or None if invalid
    """
    # Path is required
    if "path" not in data:
        return None

    path = str(data["path"]).strip()
    if not path:
        return None

    # Extract or infer type
    artifact_type = data.get("type", "").strip()
    if not artifact_type:
        # Try to infer from file extension
        try:
            artifact_type = ArtifactType.from_file_extension(Path(path).suffix).value
        except Exception:
            artifact_type = "document"  # Default fallback

    # Extract description
    description = data.get("description", "").strip()
    if not description:
        # Use name if available, or generate from filename
        name = data.get("name", Path(path).stem)
        description = f"Artifact: {name}"

    return {
        "path": path,
        "type": artifact_type,
        "description": description,
        "name": data.get("name", Path(path).stem)
    }


def _validate_artifact_path(declaration: Dict[str, str], execution_dir: Path) -> bool:
    """
    Validate that artifact path exists and is inside execution directory.

    Args:
        declaration: Artifact declaration with path
        execution_dir: Execution directory path

    Returns:
        True if valid, False otherwise
    """
    try:
        path = Path(declaration["path"])

        # Must be absolute path
        if not path.is_absolute():
            return False

        # Must exist as a file
        if not path.exists() or not path.is_file():
            return False

        # Must be inside execution directory
        try:
            path.relative_to(execution_dir)
            return True
        except ValueError:
            # Path is outside execution directory
            return False

    except Exception:
        return False


async def parse_and_register_artifacts(
    text: str,
    execution_id: str
) -> int:
    """
    Parse LLM output text for artifact declarations and register them.

    Deduplication: Skips artifacts already registered (by priority registration,
    tool output detection, or filesystem scanner).

    Args:
        text: LLM output text to parse
        execution_id: Execution ID for context

    Returns:
        Number of artifacts successfully registered
    """
    if not text or not text.strip():
        return 0

    # Get ExecutionContext
    try:
        ctx = ExecutionContext.get()
        if not ctx or not ctx.artifact_registry or not ctx.file_storage:
            logger.debug("No artifact registry available for text parser")
            return 0
    except Exception as e:
        logger.debug(f"Could not get ExecutionContext for text parser: {e}")
        return 0

    # Parse all formats
    execution_dir = Path(ctx.file_storage.root)
    declarations = parse_all_formats(text, execution_dir)

    if not declarations:
        return 0

    # Register with deduplication
    artifact_builder = ArtifactBuilder()
    registry = ctx.artifact_registry
    registered_count = 0

    for declaration in declarations:
        try:
            file_path = declaration["path"]

            # Check if already registered (deduplication)
            existing = await registry.get_by_path(file_path)
            if existing:
                logger.debug(
                    f"Artifact already registered, skipping: {file_path}",
                    existing_name=existing.name,
                    detected_by="text_parser"
                )
                continue

            # Parse artifact type
            try:
                artifact_type = ArtifactType.from_string(declaration["type"])
            except ValueError:
                # Fallback to extension-based inference
                artifact_type = ArtifactType.from_file_extension(Path(file_path).suffix)

            # Build artifact
            artifact = await artifact_builder.build(
                name=declaration.get("name", Path(file_path).stem),
                artifact_type=artifact_type,
                storage_path=file_path,
                created_by_task=execution_id or ctx.execution_id,
                created_by_module="text_parser",
                description=declaration["description"],
                derived_from=[],
            )

            # Register
            await registry.register(artifact)
            registered_count += 1

            logger.debug(
                f"Text parser registered artifact: {artifact.name}",
                artifact_type=artifact_type.value,
                path=file_path
            )

        except Exception as e:
            logger.warning(
                f"Failed to register parsed artifact: {declaration.get('path')}",
                error=str(e)
            )

    if registered_count > 0:
        logger.info(
            f"Text parser registered {registered_count} artifact(s)",
            execution_id=execution_id
        )

    return registered_count
