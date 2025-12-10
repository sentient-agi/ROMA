"""Base class for ROMA MCP servers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from loguru import logger


class TemplateResult(BaseModel):
    """Result from a template generation."""

    filename: str = Field(..., description="Name of the generated file")
    content: str = Field(..., description="Generated file content")
    language: str = Field(..., description="Programming language or file type")
    path: Optional[str] = Field(None, description="Suggested path for the file")
    dependencies: List[str] = Field(default_factory=list, description="Required dependencies")


class GenerationResult(BaseModel):
    """Result from a code generation operation."""

    files: List[TemplateResult] = Field(default_factory=list, description="Generated files")
    instructions: Optional[str] = Field(None, description="Setup or usage instructions")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Package dependencies with versions")


class BaseMCPServer(ABC):
    """Base class for ROMA MCP servers.

    MCP servers provide domain-specific code generation tools that can be
    invoked by the PTC agent during SaaS scaffolding.
    """

    # Server metadata
    name: str = "base"
    description: str = "Base MCP server"
    version: str = "1.0.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the MCP server.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._tools: Dict[str, callable] = {}
        self._register_tools()
        logger.debug(f"Initialized {self.name} MCP server with {len(self._tools)} tools")

    @abstractmethod
    def _register_tools(self) -> None:
        """Register all available tools for this server."""
        pass

    def get_tools(self) -> Dict[str, callable]:
        """Get all registered tools.

        Returns:
            Dictionary mapping tool names to callables
        """
        return self._tools.copy()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get JSON schemas for all tools (MCP format).

        Returns:
            List of tool schema dictionaries
        """
        schemas = []
        for name, tool in self._tools.items():
            schema = {
                "name": name,
                "description": tool.__doc__ or f"Tool: {name}",
            }
            # Extract parameter info from type hints if available
            if hasattr(tool, "__annotations__"):
                schema["inputSchema"] = {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            schemas.append(schema)
        return schemas

    async def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found in {self.name} server")

        tool = self._tools[name]
        logger.debug(f"Invoking tool {name} with args: {arguments}")

        # Handle both sync and async tools
        import asyncio
        if asyncio.iscoroutinefunction(tool):
            return await tool(**arguments)
        return tool(**arguments)

    def _register_tool(self, name: str, func: callable) -> None:
        """Register a tool function.

        Args:
            name: Tool name
            func: Tool function
        """
        self._tools[name] = func
        logger.debug(f"Registered tool: {name}")
