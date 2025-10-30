"""MCP-specific exceptions for tool execution errors."""


class MCPToolError(Exception):
    """Raised when MCP tool execution fails (isError=True in response).

    This exception indicates that the MCP tool itself reported a failure,
    not a protocol or transport error. The error message typically comes
    from the tool's response content.

    Examples:
        - API authentication failures
        - Invalid parameters detected by tool
        - Tool-specific business logic errors
    """
    pass


class MCPToolTimeoutError(MCPToolError):
    """Raised when MCP tool execution exceeds timeout limit.

    This is a subclass of MCPToolError to allow catching both timeout
    and general tool errors with a single except clause if needed.
    """
    pass


class MCPConnectionError(MCPToolError):
    """Raised when MCP client connection is lost or unavailable.

    This exception indicates connection-level failures such as:
    - Connection closed by server
    - Network errors
    - Connection timeout
    - Stream/transport errors
    """
    pass
