"""Web search toolkits for ROMA-DSPy.

Provides web search capabilities via:
- WebSearchToolkit: Native DSPy-based search with OpenRouter or OpenAI
- SerperToolkit: Traditional Serper API search
"""

from roma_dspy.tools.web_search.serper import SerperToolkit
from roma_dspy.tools.web_search.toolkit import WebSearchProvider, WebSearchToolkit

__all__ = ["WebSearchToolkit", "WebSearchProvider", "SerperToolkit"]
