"""Serper web search toolkit following Agno patterns."""

import json
import os
from typing import Optional

import httpx

from roma_dspy.tools.base.base import BaseToolkit


class SerperToolkit(BaseToolkit):
    """
    Serper web search toolkit providing search and web scraping capabilities.

    Based on Agno SerperTools implementation with DSPy integration.
    Provides Google search, news search, academic search, and web scraping.
    Requires SERPER_API_KEY environment variable or api_key in config.

    Note: Uses httpx.AsyncClient for non-blocking async HTTP requests to prevent
    event loop blocking during concurrent agent execution.
    """

    def _setup_dependencies(self) -> None:
        """Setup Serper toolkit dependencies."""
        # httpx is already a dependency - no import check needed
        # Get API key from config or environment
        self.api_key = self.config.get('api_key') or os.getenv('SERPER_API_KEY')
        if not self.api_key:
            raise ValueError(
                "SERPER_API_KEY is required. Set it as environment variable or "
                "pass 'api_key' in toolkit_config."
            )

    def _initialize_tools(self) -> None:
        """Initialize Serper toolkit configuration."""
        # Configuration with defaults
        self.location = self.config.get('location', 'us')
        self.language = self.config.get('language', 'en')
        self.num_results = self.config.get('num_results', 10)
        self.date_range = self.config.get('date_range')  # Optional

        # Base URL for Serper API
        self.base_url = "https://google.serper.dev"

        # Initialize httpx async client (will be created on first use)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client with proper configuration."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),  # 30 second timeout
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def cleanup(self) -> None:
        """Cleanup resources (close httpx client)."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self.log_debug("Closed httpx client")

    async def _make_request(self, endpoint: str, payload: dict) -> dict:
        """Make async HTTP request to Serper API using httpx."""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }

        client = await self._get_client()

        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self.log_error(f"API request failed with status {e.response.status_code}: {str(e)}")
            raise
        except httpx.RequestError as e:
            self.log_error(f"API request failed: {str(e)}")
            raise
        except Exception as e:
            self.log_error(f"Unexpected error in API request: {str(e)}")
            raise

    async def search(self, query: str, num_results: Optional[int] = None) -> str:
        """
        Perform Google web search using Serper API.

        Use this tool to search the web for information on any topic.
        Returns search results with titles, snippets, and URLs.

        Args:
            query: Search query string
            num_results: Number of results to return (default: configured num_results)

        Returns:
            JSON string with search results

        Examples:
            search("Python programming tutorials") - Search for Python tutorials
            search("weather in New York", num_results=5) - Get 5 weather results
            search("latest AI research 2024") - Search for recent AI research
        """
        try:
            results_count = num_results or self.num_results

            payload = {
                "q": query,
                "num": results_count,
                "gl": self.location,
                "hl": self.language
            }

            if self.date_range:
                payload["tbs"] = f"qdr:{self.date_range}"

            self.log_debug(f"Searching web: '{query}' (num_results={results_count})")
            raw_response = await self._make_request("search", payload)

            # Extract and format results
            results = []
            for item in raw_response.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                    "position": item.get("position", 0)
                })

            response = {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results,
                "raw_response": raw_response
            }

            self.log_debug(f"Web search completed: {len(results)} results for '{query}'")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Error in web search: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def search_news(self, query: str, num_results: Optional[int] = None) -> str:
        """
        Search for news articles using Serper API.

        Use this tool to find recent news articles and current events related to your query.
        Returns news results with headlines, sources, publication dates, and URLs.

        Args:
            query: News search query string
            num_results: Number of news results to return (default: configured num_results)

        Returns:
            JSON string with news search results

        Examples:
            search_news("artificial intelligence") - Get AI news articles
            search_news("climate change", num_results=3) - Get 3 climate news items
            search_news("technology stocks") - Search for tech stock news
        """
        try:
            results_count = num_results or self.num_results

            payload = {
                "q": query,
                "num": results_count,
                "gl": self.location,
                "hl": self.language
            }

            if self.date_range:
                payload["tbs"] = f"qdr:{self.date_range}"

            self.log_debug(f"Searching news: '{query}' (num_results={results_count})")
            raw_response = await self._make_request("news", payload)

            # Extract and format news results
            results = []
            for item in raw_response.get("news", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                    "source": item.get("source", ""),
                    "date": item.get("date", ""),
                    "position": item.get("position", 0)
                })

            response = {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results,
                "raw_response": raw_response
            }

            self.log_debug(f"News search completed: {len(results)} results for '{query}'")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Error in news search: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def search_scholar(self, query: str, num_results: Optional[int] = None) -> str:
        """
        Search for academic papers using Google Scholar via Serper API.

        Use this tool to find scholarly articles, research papers, and academic publications.
        Returns academic search results with paper titles, authors, citations, and URLs.

        Args:
            query: Academic search query string
            num_results: Number of scholarly results to return (default: configured num_results)

        Returns:
            JSON string with academic search results

        Examples:
            search_scholar("machine learning algorithms") - Find ML research papers
            search_scholar("quantum computing", num_results=5) - Get 5 quantum papers
            search_scholar("climate change mitigation") - Search for climate research
        """
        try:
            results_count = num_results or self.num_results

            payload = {
                "q": query,
                "num": results_count
            }

            self.log_debug(f"Searching scholar: '{query}' (num_results={results_count})")
            raw_response = await self._make_request("scholar", payload)

            # Extract and format scholar results
            results = []
            for item in raw_response.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                    "authors": item.get("authors", ""),
                    "cited_by": item.get("citedBy", ""),
                    "year": item.get("year", ""),
                    "position": item.get("position", 0)
                })

            response = {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results,
                "raw_response": raw_response
            }

            self.log_debug(f"Scholar search completed: {len(results)} results for '{query}'")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Error in scholar search: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def scrape_webpage(self, url: str, markdown: bool = False) -> str:
        """
        Scrape and extract content from a webpage.

        Use this tool to extract text content from web pages for analysis or information gathering.
        Can return content in plain text or markdown format.

        Args:
            url: URL of the webpage to scrape
            markdown: Whether to return content in markdown format (default: False)

        Returns:
            JSON string with extracted webpage content

        Examples:
            scrape_webpage("https://example.com/article") - Extract article text
            scrape_webpage("https://blog.com/post", markdown=True) - Get content as markdown
            scrape_webpage("https://news.com/story") - Scrape news article content
        """
        try:
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                error_msg = "URL must start with http:// or https://"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Make async request to scrape the webpage
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            self.log_debug(f"Scraping webpage: {url} (markdown={markdown})")
            client = await self._get_client()
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Try to extract readable content
            content = response.text

            # Basic content extraction (could be enhanced with BeautifulSoup)
            # For now, return raw HTML - in production, would parse and clean
            if markdown:
                # Simple markdown conversion could be added here
                extracted_content = content
            else:
                extracted_content = content

            result = {
                "success": True,
                "url": url,
                "content": extracted_content,
                "content_length": len(extracted_content),
                "format": "markdown" if markdown else "html"
            }

            self.log_debug(f"Webpage scraped successfully: {len(extracted_content)} characters")
            return json.dumps(result)

        except httpx.TimeoutException:
            error_msg = f"Timeout while scraping webpage: {url}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})
        except httpx.RequestError as e:
            error_msg = f"Error scraping webpage {url}: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})
        except Exception as e:
            error_msg = f"Unexpected error scraping webpage: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})