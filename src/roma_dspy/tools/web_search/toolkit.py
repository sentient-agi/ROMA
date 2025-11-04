"""Web search toolkit using DSPy Predict with web search enabled models."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional

import dspy
from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage


class WebSearchProvider(str, Enum):
    """Web search provider backends."""

    OPENROUTER = "openrouter"
    OPENAI = "openai"


class WebSearchSignature(dspy.Signature):
    """You are an expert data searcher with 20+ years of experience in searching and retrieving information from reliable sources.

    Your task is to RETRIEVE and FETCH all necessary data to answer the query. Focus on comprehensive data retrieval, not reasoning or analysis.

    Guidelines:
    1. COMPREHENSIVE DATA RETRIEVAL:
       - If it's a table, retrieve the ENTIRE table (even if it has 50, 100, or more rows)
       - If it's a list, include ALL items in the list
       - If it's statistics or rankings, include ALL available data points
       - For articles/paragraphs, include ALL relevant sections and mentions
       - Present data in its complete form - do not truncate or summarize

    2. SOURCE RELIABILITY PRIORITY:
       - Wikipedia is the MOST PREFERRED source when available
       - Other reputable sources in order of preference:
         • Official government databases and statistics
         • Academic institutions and research papers
         • Established news organizations (BBC, Reuters, AP, etc.)
         • Industry-standard databases and professional organizations
       - Always cite your sources

    3. DATA PRESENTATION:
       - Present data EXACTLY as found in the source
       - Maintain original formatting (tables, lists, etc.)
       - Include all columns, rows, and data points
       - Do NOT analyze, interpret, or reason about the data
       - Do NOT summarize or condense - present everything

    4. TEMPORAL AWARENESS:
       - Prioritize recent information when relevant
       - When data has timestamps or dates, include them
       - For time-sensitive queries, focus on the most current available data
    """

    query: str = dspy.InputField(
        desc="The search query or question to answer. Use this to search for comprehensive data from reliable sources."
    )
    answer: str = dspy.OutputField(
        desc="Complete and comprehensive data retrieved from web search results. Include ALL relevant facts, details, tables, lists, and data points. Present data EXACTLY as found in sources without summarizing or analyzing. Maintain original formatting."
    )
    citations: list[str] = dspy.OutputField(
        desc="List of source URLs used to generate the answer. Prioritize Wikipedia and other reliable sources (government databases, academic institutions, established news organizations)."
    )

# near other signature definitions
class PlainWebSearchSignature(dspy.Signature):
    """You are an expert data searcher with 20+ years of experience in searching and retrieving information from reliable sources.

    Your task is to RETRIEVE and FETCH all necessary data to answer the query. Focus on comprehensive data retrieval, not reasoning or analysis.

    Guidelines:
    1. COMPREHENSIVE DATA RETRIEVAL:
       - If it's a table, retrieve the ENTIRE table (even if it has 50, 100, or more rows)
       - If it's a list, include ALL items in the list
       - If it's statistics or rankings, include ALL available data points
       - For articles/paragraphs, include ALL relevant sections and mentions
       - Present data in its complete form - do not truncate or summarize

    2. SOURCE RELIABILITY PRIORITY:
       - Wikipedia is the MOST PREFERRED source when available
       - Other reputable sources in order of preference:
         • Official government databases and statistics
         • Academic institutions and research papers
         • Established news organizations (BBC, Reuters, AP, etc.)
         • Industry-standard databases and professional organizations
       - Always cite your sources

    3. DATA PRESENTATION:
       - Present data EXACTLY as found in the source
       - Maintain original formatting (tables, lists, etc.)
       - Include all columns, rows, and data points
       - Do NOT analyze, interpret, or reason about the data
       - Do NOT summarize or condense - present everything

    4. TEMPORAL AWARENESS:
       - Prioritize recent information when relevant
       - When data has timestamps or dates, include them
       - For time-sensitive queries, focus on the most current available data
    """

    query: str = dspy.InputField(desc="Search query.")
    answer: str = dspy.OutputField(desc="Answer text with sources inline if possible.")



class WebSearchToolkit(BaseToolkit):
    """Web search toolkit using DSPy with web-search-enabled language models.

    Provides web search capabilities by configuring a DSPy language model with
    web search features (OpenRouter plugins or OpenAI web_search_preview).

    The toolkit uses `dspy.Predict` with a web search signature, allowing the
    language model to search the web and incorporate real-time information into
    its responses. Citations are automatically extracted from the LM response.

    Configuration:
        model: Model to use for web search (e.g., "openai/gpt-4o", "anthropic/claude-sonnet-4")
        provider: WebSearchProvider.OPENROUTER or WebSearchProvider.OPENAI (default: OPENROUTER)
        search_engine: Search engine for OpenRouter ("exa" recommended)
        search_context_size: "low", "medium", or "high" (default: "medium")
        max_results: Maximum search results to include (default: 5)
        temperature: Model temperature (default: 0.0 for deterministic results)
        max_tokens: Maximum tokens in response (default: 4000)

    Example:
        ```yaml
        toolkits:
          - class_name: WebSearchToolkit
            toolkit_config:
              model: openrouter/anthropic/claude-sonnet-4
              provider: openrouter  # or "openai"
              search_engine: exa
              search_context_size: medium
              max_results: 5
        ```

    Usage:
        ```python
        result = await toolkit.web_search(
            query="What is the current price of Bitcoin?"
        )
        # Returns: {
        #   success: True,
        #   data: "Bitcoin is currently...",
        #   citations: [{url: "...", title: "..."}],
        #   ...
        # }
        ```
    """

    def __init__(
        self,
        model: str,
        search_engine: str = "exa",
        search_context_size: str = "medium",
        max_results: int = 5,
        temperature: float = 0.0,
        max_tokens: int = 4000,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        file_storage: Optional["FileStorage"] = None,
        **config,
    ):
        """Initialize web search toolkit.

        Args:
            model: Language model to use (must support web search)
                   - OpenRouter models: "openrouter/..." (uses plugins)
                   - OpenAI models: "openai/..." (uses Responses API)
            search_engine: Search engine for OpenRouter ("exa" recommended, omit for native)
            search_context_size: Context depth - "low", "medium", or "high"
            max_results: Maximum number of search results to include
            temperature: Model temperature for response generation
            max_tokens: Maximum tokens in model response
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include (None = all)
            exclude_tools: Tools to exclude
            file_storage: Optional file storage for large responses
            **config: Additional configuration
        """
        self.model = model
        self._chat_adapter = dspy.ChatAdapter(use_native_function_calling=True)

        # Auto-detect provider from model identifier
        if model.startswith("openrouter/"):
            self.provider = WebSearchProvider.OPENROUTER
        elif model.startswith("openai/"):
            self.provider = WebSearchProvider.OPENAI
        else:
            raise ValueError(
                f"Invalid model identifier: {model}. "
                "Must start with 'openrouter/' or 'openai/'"
            )

        self.search_engine = search_engine
        self.search_context_size = search_context_size
        self.max_results = max_results
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Validate search context size
        if search_context_size not in ("low", "medium", "high"):
            raise ValueError(
                f"Invalid search_context_size: {search_context_size}. "
                "Must be 'low', 'medium', or 'high'"
            )

        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            file_storage=file_storage,
            **config,
        )

        logger.info(
            f"Initialized WebSearchToolkit: model={model}, provider={self.provider.value}, "
            f"engine={search_engine}, max_results={max_results}"
        )

    def _setup_dependencies(self) -> None:
        """Setup external dependencies - DSPy is always available."""
        pass

    def _initialize_tools(self) -> None:
        """Initialize web search predictor with configured LM."""
        # Build LM configuration based on provider
        if self.provider == WebSearchProvider.OPENROUTER:
            # OpenRouter uses plugins parameter
            web_config = {
                "id": "web",
                "engine": self.search_engine,
                "max_results": self.max_results,
            }

            # Add search context size if not default
            if self.search_context_size != "medium":
                web_config["search_context_size"] = self.search_context_size

            # Create LM with plugins in extra_body
            self.lm = dspy.LM(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body={"plugins": [web_config]},
            )

        elif self.provider == WebSearchProvider.OPENAI:
            # OpenAI uses web_search tool in Responses API
            # Format: tools=[{"type": "web_search", "search_context_size": "low"}]
            # Reference: https://platform.openai.com/docs/guides/tools-web-search
            tool_config = {"type": "web_search"}

            # Add search context size if not default
            if self.search_context_size != "medium":
                tool_config["search_context_size"] = self.search_context_size

            self.lm = dspy.LM(
                model=self.model,
                model_type="responses",  # OpenAI Responses API
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tools=[tool_config],
                tool_choice={"type": "web_search"},  # Force use of web search tool
            )
            # Use plain text signature to avoid structured-output/JSON mode
            self.predictor = dspy.Predict(PlainWebSearchSignature)
            self.predictor.lm = self.lm
            return


        # Create web search predictor
        self.predictor = dspy.Predict(WebSearchSignature)
        self.predictor.lm = self.lm

        logger.debug(
            f"Initialized web search predictor with {self.provider.value} provider"
        )

    async def web_search(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_context_size: Optional[str] = None,
    ) -> dict:
        """Search the web and return a comprehensive answer with citations.

        Uses the configured language model with web search enabled to answer
        the query based on current information from the web. Automatically
        extracts citations from the response.

        Args:
            query: The search query or question to answer
            max_results: Override default max_results for this search
            search_context_size: Override default search_context_size ("low", "medium", "high")

        Returns:
            dict: Tool response with format:
                {
                    "success": True,
                    "data": "answer text",
                    "citations": [{"url": "...", "title": "..."}],  # If available
                    "tool_name": "web_search",
                    "query": "original query",
                    "model": "model used",
                    "provider": "openrouter" or "openai"
                }

        Example:
            ```python
            result = await toolkit.web_search(
                query="What are the latest developments in quantum computing?",
                max_results=10
            )

            if result["success"]:
                print(result["data"])  # Answer
                print(result.get("citations", []))  # Source URLs
            ```
        """
        try:
            logger.info(
                f"Executing web search: query='{query[:100]}...', "
                f"max_results={max_results or self.max_results}"
            )

            # Build predictor kwargs
            kwargs = {}

            # If parameters override defaults, create new LM with updated config
            if max_results is not None or search_context_size is not None:
                lm = self._create_lm_with_overrides(max_results, search_context_size)
                kwargs["lm"] = lm

            # Execute prediction
            with dspy.context(lm=self.lm, adapter=self._chat_adapter):
                prediction = await self.predictor.acall(query=query, **kwargs)

            # Extract answer
            answer = prediction.answer

            # Extract citations from signature output (DSPy extracts as list[str])
            citations_urls = getattr(prediction, "citations", [])

            # Convert to citation dicts format
            citations = [{"url": url} for url in citations_urls] if citations_urls else []

            logger.success(
                f"Web search completed: {len(answer)} chars, "
                f"{len(citations)} citations"
            )

            # Build response with citations
            response = await self._build_success_response(
                data=answer,
                tool_name="web_search",
                query=query,
                model=self.model,
                provider=self.provider.value,
            )

            # Add citations if available
            if citations:
                response["citations"] = citations

            return response

        except Exception as e:
            logger.error(f"Web search failed for query '{query[:100]}...': {e}")
            return self._build_error_response(
                e, tool_name="web_search", query=query
            )

    def _extract_citations(self, prediction: dspy.Prediction) -> List[Dict[str, str]]:
        """Extract citations from DSPy Prediction object.

        DSPy automatically extracts citations from LiteLLM responses and stores
        them in the completions metadata.

        Args:
            prediction: DSPy Prediction object

        Returns:
            List of citation dicts with 'url' and optionally 'title'
        """
        citations = []

        try:
            # Access completions from prediction
            if hasattr(prediction, "completions") and prediction.completions:
                for completion in prediction.completions:
                    # Check if completion has citations
                    if isinstance(completion, dict) and "citations" in completion:
                        citations.extend(completion["citations"])

            # Deduplicate by URL
            seen_urls = set()
            unique_citations = []
            for citation in citations:
                url = citation.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_citations.append(citation)

            logger.debug(f"Extracted {len(unique_citations)} unique citations")
            return unique_citations

        except Exception as e:
            logger.warning(f"Failed to extract citations: {e}")
            return []

    def _create_lm_with_overrides(
        self,
        max_results: Optional[int] = None,
        search_context_size: Optional[str] = None,
    ) -> dspy.LM:
        """Create LM with parameter overrides.

        Args:
            max_results: Override max_results
            search_context_size: Override search_context_size

        Returns:
            New LM instance with updated configuration
        """
        effective_max_results = max_results or self.max_results
        effective_context_size = search_context_size or self.search_context_size

        if self.provider == WebSearchProvider.OPENROUTER:
            web_config = {
                "id": "web",
                "engine": self.search_engine,
                "max_results": effective_max_results,
            }

            if effective_context_size != "medium":
                web_config["search_context_size"] = effective_context_size

            return dspy.LM(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body={"plugins": [web_config]},
            )

        elif self.provider == WebSearchProvider.OPENAI:
            tool_config = {"type": "web_search"}

            if effective_context_size != "medium":
                tool_config["search_context_size"] = effective_context_size

            return dspy.LM(
                model=self.model,
                model_type="responses",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tools=[tool_config],
                tool_choice={"type": "web_search"},  # Force use of web search tool
            )


__all__ = ["WebSearchToolkit", "WebSearchProvider"]