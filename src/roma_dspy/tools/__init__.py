"""Toolkit system for ROMA-DSPy agents.

This module provides a flexible toolkit system for adding tools to DSPy agents.
Toolkits are collections of related tools that follow the Agno pattern with
DSPy integration.

Available toolkits:
- FileToolkit: File system operations (builtin)
- ArtifactToolkit: Artifact registration and management (builtin, mandatory for Executor/Aggregator)
- CalculatorToolkit: Mathematical operations
- WebSearchToolkit: Native web search via OpenRouter/OpenAI (DSPy-based)
- SerperToolkit: Web search and scraping via Serper API
- E2BToolkit: Code execution in secure sandboxes (requires e2b extra)

Crypto & DeFi toolkits:
- BinanceToolkit: Cryptocurrency market data from Binance
- CoinGeckoToolkit: Cryptocurrency prices and market data
- DefiLlamaToolkit: DeFi protocol TVL, fees, and yield data
- ArkhamToolkit: Blockchain analytics with on-chain intelligence
- CoinglassToolkit: Derivatives and futures market data

Install E2B toolkit:
    pip install -e ".[e2b]"

Example usage:
    from roma_dspy.tools import register_toolkit, CalculatorToolkit
    from roma_dspy.config.schemas.toolkit import ToolkitConfig

    # Register external toolkits (optional - auto-registered from imports)
    register_toolkit(CalculatorToolkit)

    # Configure toolkit in agent config YAML:
    # toolkits:
    #   - class_name: "CalculatorToolkit"
    #     enabled: true
    #     exclude_tools: ["factorial"]
    #     toolkit_config:
    #       precision: 5
"""

from .base import BaseToolkit, ToolkitManager
from .core import FileToolkit, CalculatorToolkit, E2BToolkit, ArtifactToolkit
from .web_search import WebSearchToolkit, WebSearchProvider, SerperToolkit
from .crypto import (
    BinanceToolkit,
    CoinGeckoToolkit,
    DefiLlamaToolkit,
    ArkhamToolkit,
    CoinglassToolkit,
)


def register_toolkit(toolkit_class: type) -> None:
    """
    Register an external toolkit class for use in configurations.

    Args:
        toolkit_class: Toolkit class that inherits from BaseToolkit

    Example:
        from roma_dspy.tools import register_toolkit
        from my_project.custom_toolkit import CustomToolkit

        register_toolkit(CustomToolkit)
    """
    if not issubclass(toolkit_class, BaseToolkit):
        raise ValueError(f"Toolkit class {toolkit_class.__name__} must inherit from BaseToolkit")

    manager = ToolkitManager.get_instance()
    manager.register_external_toolkit(toolkit_class.__name__, toolkit_class)


# External toolkits need to be registered explicitly or during first use
# to avoid circular import issues during module initialization


__all__ = [
    "BaseToolkit",
    "ToolkitManager",
    "FileToolkit",
    "CalculatorToolkit",
    "ArtifactToolkit",
    "WebSearchToolkit",
    "WebSearchProvider",
    "SerperToolkit",
    "E2BToolkit",
    "BinanceToolkit",
    "CoinGeckoToolkit",
    "DefiLlamaToolkit",
    "ArkhamToolkit",
    "CoinglassToolkit",
    "register_toolkit",
]