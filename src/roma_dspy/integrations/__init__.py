"""External service integrations for ROMA."""

from roma_dspy.integrations.ptc_client import PTCClient, get_ptc_client

try:
    from roma_dspy.integrations.ace_integration import (
        ACEIntegratedExecutor,
        CodeGenerationEnvironment,
        ACEPTCAgent,
        create_ace_executor,
        ACE_AVAILABLE,
    )
    __all__ = [
        "PTCClient",
        "get_ptc_client",
        "ACEIntegratedExecutor",
        "CodeGenerationEnvironment",
        "ACEPTCAgent",
        "create_ace_executor",
        "ACE_AVAILABLE",
    ]
except ImportError:
    # ACE not installed
    __all__ = ["PTCClient", "get_ptc_client"]
