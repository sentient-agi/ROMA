"""Unit tests for SerperToolkit with async httpx."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from roma_dspy.tools.web_search.serper import SerperToolkit


@pytest.fixture
def serper_toolkit():
    """Create a SerperToolkit instance for testing."""
    config = {
        'api_key': 'test_key_123',
        'location': 'us',
        'language': 'en',
        'num_results': 10
    }
    toolkit = SerperToolkit(
        enabled=True,
        include_tools=None,
        exclude_tools=None,
        **config
    )
    return toolkit


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


class TestSerperToolkitInitialization:
    """Test SerperToolkit initialization."""

    def test_init_with_api_key(self):
        """Test toolkit initialization with API key."""
        toolkit = SerperToolkit(
            enabled=True,
            api_key='test_key'
        )
        assert toolkit.api_key == 'test_key'
        assert toolkit.location == 'us'
        assert toolkit.language == 'en'
        assert toolkit.num_results == 10

    def test_init_with_custom_config(self):
        """Test toolkit initialization with custom configuration."""
        toolkit = SerperToolkit(
            enabled=True,
            api_key='test_key',
            location='uk',
            language='fr',
            num_results=5
        )
        assert toolkit.location == 'uk'
        assert toolkit.language == 'fr'
        assert toolkit.num_results == 5

    @patch.dict('os.environ', {}, clear=True)  # Clear env vars
    def test_init_without_api_key_raises(self):
        """Test that initialization without API key raises ValueError."""
        with pytest.raises(ValueError, match="SERPER_API_KEY is required"):
            SerperToolkit(enabled=True)

    @patch.dict('os.environ', {'SERPER_API_KEY': 'env_key'})
    def test_init_with_env_api_key(self):
        """Test toolkit initialization with API key from environment."""
        toolkit = SerperToolkit(enabled=True)
        assert toolkit.api_key == 'env_key'


class TestSerperToolkitClientManagement:
    """Test httpx client management."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(self, serper_toolkit):
        """Test that _get_client creates a new httpx.AsyncClient."""
        client = await serper_toolkit._get_client()

        assert isinstance(client, httpx.AsyncClient)
        assert serper_toolkit._client is client

        # Cleanup
        await serper_toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_get_client_reuses_existing_client(self, serper_toolkit):
        """Test that _get_client reuses existing client."""
        client1 = await serper_toolkit._get_client()
        client2 = await serper_toolkit._get_client()

        assert client1 is client2

        # Cleanup
        await serper_toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self, serper_toolkit):
        """Test that cleanup closes the httpx client."""
        await serper_toolkit._get_client()
        assert serper_toolkit._client is not None

        await serper_toolkit.cleanup()
        assert serper_toolkit._client is None

    @pytest.mark.asyncio
    async def test_cleanup_without_client(self, serper_toolkit):
        """Test that cleanup handles no client gracefully."""
        assert serper_toolkit._client is None
        await serper_toolkit.cleanup()  # Should not raise


class TestSerperToolkitSearch:
    """Test web search functionality."""

    @pytest.mark.asyncio
    async def test_search_success(self, serper_toolkit, mock_httpx_client):
        """Test successful web search."""
        # Mock response - json() returns a dict directly (not awaitable in httpx)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Test Result 1",
                    "snippet": "Test snippet 1",
                    "link": "https://example.com/1",
                    "position": 1
                },
                {
                    "title": "Test Result 2",
                    "snippet": "Test snippet 2",
                    "link": "https://example.com/2",
                    "position": 2
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        # Patch the client
        serper_toolkit._client = mock_httpx_client

        # Execute search
        result_json = await serper_toolkit.search("test query")
        result = json.loads(result_json)

        # Verify
        assert result["success"] is True
        assert result["query"] == "test query"
        assert result["results_count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Test Result 1"

    @pytest.mark.asyncio
    async def test_search_with_custom_num_results(self, serper_toolkit, mock_httpx_client):
        """Test search with custom number of results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        serper_toolkit._client = mock_httpx_client

        await serper_toolkit.search("test query", num_results=5)

        # Verify payload contains custom num_results
        call_args = mock_httpx_client.post.call_args
        payload = call_args[1]['json']
        assert payload['num'] == 5

    @pytest.mark.asyncio
    async def test_search_error_handling(self, serper_toolkit, mock_httpx_client):
        """Test search error handling."""
        mock_httpx_client.post.side_effect = httpx.RequestError("Connection failed")

        serper_toolkit._client = mock_httpx_client

        result_json = await serper_toolkit.search("test query")
        result = json.loads(result_json)

        assert result["success"] is False
        assert "error" in result


class TestSerperToolkitSearchNews:
    """Test news search functionality."""

    @pytest.mark.asyncio
    async def test_search_news_success(self, serper_toolkit, mock_httpx_client):
        """Test successful news search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "news": [
                {
                    "title": "News Article 1",
                    "snippet": "News snippet 1",
                    "link": "https://news.com/1",
                    "source": "News Source",
                    "date": "2024-01-01",
                    "position": 1
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        serper_toolkit._client = mock_httpx_client

        result_json = await serper_toolkit.search_news("test news query")
        result = json.loads(result_json)

        assert result["success"] is True
        assert result["results_count"] == 1
        assert result["results"][0]["source"] == "News Source"
        assert result["results"][0]["date"] == "2024-01-01"


class TestSerperToolkitSearchScholar:
    """Test scholar search functionality."""

    @pytest.mark.asyncio
    async def test_search_scholar_success(self, serper_toolkit, mock_httpx_client):
        """Test successful scholar search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Research Paper 1",
                    "snippet": "Paper abstract",
                    "link": "https://scholar.com/1",
                    "authors": "Author Name",
                    "citedBy": "100",
                    "year": "2023",
                    "position": 1
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        serper_toolkit._client = mock_httpx_client

        result_json = await serper_toolkit.search_scholar("machine learning")
        result = json.loads(result_json)

        assert result["success"] is True
        assert result["results"][0]["authors"] == "Author Name"
        assert result["results"][0]["cited_by"] == "100"
        assert result["results"][0]["year"] == "2023"


class TestSerperToolkitScrapeWebpage:
    """Test webpage scraping functionality."""

    @pytest.mark.asyncio
    async def test_scrape_webpage_success(self, serper_toolkit, mock_httpx_client):
        """Test successful webpage scraping."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        serper_toolkit._client = mock_httpx_client

        result_json = await serper_toolkit.scrape_webpage("https://example.com")
        result = json.loads(result_json)

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert "Test content" in result["content"]
        assert result["format"] == "html"

    @pytest.mark.asyncio
    async def test_scrape_webpage_invalid_url(self, serper_toolkit):
        """Test scraping with invalid URL."""
        result_json = await serper_toolkit.scrape_webpage("invalid-url")
        result = json.loads(result_json)

        assert result["success"] is False
        assert "must start with http" in result["error"]

    @pytest.mark.asyncio
    async def test_scrape_webpage_timeout(self, serper_toolkit, mock_httpx_client):
        """Test scraping with timeout."""
        mock_httpx_client.get.side_effect = httpx.TimeoutException("Timeout")

        serper_toolkit._client = mock_httpx_client

        result_json = await serper_toolkit.scrape_webpage("https://example.com")
        result = json.loads(result_json)

        assert result["success"] is False
        assert "Timeout" in result["error"]


class TestSerperToolkitMakeRequest:
    """Test internal _make_request method."""

    @pytest.mark.asyncio
    async def test_make_request_success(self, serper_toolkit, mock_httpx_client):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        serper_toolkit._client = mock_httpx_client

        result = await serper_toolkit._make_request("search", {"q": "test"})

        assert result == {"result": "success"}
        assert mock_httpx_client.post.called

    @pytest.mark.asyncio
    async def test_make_request_http_error(self, serper_toolkit, mock_httpx_client):
        """Test API request with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response
        )

        serper_toolkit._client = mock_httpx_client

        with pytest.raises(httpx.HTTPStatusError):
            await serper_toolkit._make_request("search", {"q": "test"})