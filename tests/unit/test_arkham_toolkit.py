"""Unit tests for Arkham Intelligence toolkit."""

import pytest
import os
from unittest.mock import MagicMock

from roma_dspy.tools.crypto.arkham import (
    ArkhamToolkit,
    ArkhamAPIClient,
    ArkhamAPIError,
)
from roma_dspy.tools.value_objects.crypto import BlockchainNetwork, ErrorType


class TestArkhamToolkit:
    """Unit tests for ArkhamToolkit."""

    def test_initialization_defaults(self):
        """Test toolkit initialization with defaults."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()

        assert toolkit.default_chain == "ethereum"
        assert toolkit.enable_analysis is True
        assert toolkit.api_key == "test_key"

    def test_initialization_custom_params(self):
        """Test toolkit initialization with custom parameters."""
        toolkit = ArkhamToolkit(
            api_key="custom_key",
            default_chain="bitcoin",
            enable_analysis=False,
        )

        assert toolkit.default_chain == "bitcoin"
        assert toolkit.enable_analysis is False
        assert toolkit.api_key == "custom_key"
        assert toolkit.stats is None

    def test_initialization_missing_api_key(self):
        """Test initialization fails without API key."""
        if "ARKHAM_API_KEY" in os.environ:
            del os.environ["ARKHAM_API_KEY"]

        with pytest.raises(ValueError, match="Arkham API key required"):
            ArkhamToolkit()

    def test_validate_chain_success(self):
        """Test chain validation with valid chain."""
        os.environ["ARKHAM_API_KEY"] = "test_key"
        toolkit = ArkhamToolkit()

        result = toolkit._validate_chain("ethereum")
        assert result == "ethereum"

        result = toolkit._validate_chain("BITCOIN")
        assert result == "bitcoin"

    def test_validate_chain_failure(self):
        """Test chain validation with invalid chain."""
        os.environ["ARKHAM_API_KEY"] = "test_key"
        toolkit = ArkhamToolkit()

        with pytest.raises(ValueError, match="Unsupported chain"):
            toolkit._validate_chain("invalid_chain")

    def test_validate_address_ethereum(self):
        """Test Ethereum address validation."""
        os.environ["ARKHAM_API_KEY"] = "test_key"
        toolkit = ArkhamToolkit()

        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"  # Valid 42-char address
        result = toolkit._validate_address(address)

        assert result.startswith("0x")
        assert len(result) == 42  # normalized to lowercase

    def test_validate_address_invalid(self):
        """Test address validation with invalid input."""
        os.environ["ARKHAM_API_KEY"] = "test_key"
        toolkit = ArkhamToolkit()

        with pytest.raises(ValueError):
            toolkit._validate_address("")

        with pytest.raises(ValueError):
            toolkit._validate_address(None)

    def test_validate_address_bitcoin_style(self):
        """Test Bitcoin-style address validation."""
        os.environ["ARKHAM_API_KEY"] = "test_key"
        toolkit = ArkhamToolkit()

        # Bitcoin address (basic validation)
        address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        result = toolkit._validate_address(address)

        assert result == address

    def test_include_tools(self):
        """Test toolkit with include_tools."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(include_tools=["get_top_tokens", "get_token_holders"])

        # Should only have included tools
        enabled_tools = toolkit.get_enabled_tools()
        assert "get_top_tokens" in enabled_tools

    def test_exclude_tools(self):
        """Test toolkit with exclude_tools."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(exclude_tools=["get_transfers"])

        enabled_tools = toolkit.get_enabled_tools()

        assert "get_transfers" not in enabled_tools

    def test_toolkit_disabled(self):
        """Test toolkit can be disabled."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(enabled=False)

        assert toolkit.enabled is False

    def test_toolkit_repr(self):
        """Test toolkit representation."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()
        repr_str = repr(toolkit)

        assert "ArkhamToolkit" in repr_str
        assert "enabled" in repr_str.lower()

    def test_client_initialization(self):
        """Test API client is initialized."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()

        assert isinstance(toolkit.client, ArkhamAPIClient)
        assert toolkit.client.api_key == "test_key"

    def test_stats_analyzer_initialization(self):
        """Test StatisticalAnalyzer initialization."""
        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(enable_analysis=True)

        assert toolkit.stats is not None

        toolkit_no_stats = ArkhamToolkit(enable_analysis=False)
        assert toolkit_no_stats.stats is None


class TestArkhamAPIClient:
    """Unit tests for ArkhamAPIClient."""

    def test_client_initialization(self):
        """Test API client initialization."""
        client = ArkhamAPIClient(api_key="test_key")

        assert client.api_key == "test_key"
        assert client.base_url == "https://api.arkm.com"

    def test_client_initialization_from_env(self):
        """Test API client reads from environment."""
        os.environ["ARKHAM_API_KEY"] = "env_key"

        client = ArkhamAPIClient()

        assert client.api_key == "env_key"

    def test_client_missing_api_key(self):
        """Test client fails without API key."""
        if "ARKHAM_API_KEY" in os.environ:
            del os.environ["ARKHAM_API_KEY"]

        with pytest.raises(ValueError, match="Arkham API key required"):
            ArkhamAPIClient()

    def test_client_custom_base_url(self):
        """Test client with custom base URL."""
        client = ArkhamAPIClient(api_key="test_key", base_url="https://custom.api.url")

        assert client.base_url == "https://custom.api.url"


class TestArkhamAPIError:
    """Unit tests for ArkhamAPIError."""

    def test_error_creation(self):
        """Test error creation."""
        error = ArkhamAPIError("Test error")

        assert str(error) == "[api_error] Test error"
        assert error.error_type == ErrorType.API_ERROR

    def test_error_with_status_code(self):
        """Test error with status code."""
        error = ArkhamAPIError(
            "Test error", status_code=404, error_type=ErrorType.NOT_FOUND_ERROR
        )

        assert error.status_code == 404
        assert error.error_type == ErrorType.NOT_FOUND_ERROR
        assert "HTTP 404" in str(error)

    def test_error_types(self):
        """Test different error types."""
        error_auth = ArkhamAPIError(
            "Auth error", error_type=ErrorType.AUTHENTICATION_ERROR
        )
        assert error_auth.error_type == ErrorType.AUTHENTICATION_ERROR

        error_rate = ArkhamAPIError("Rate limit", error_type=ErrorType.RATE_LIMIT_ERROR)
        assert error_rate.error_type == ErrorType.RATE_LIMIT_ERROR


def test_value_object_imports():
    """Test that value objects can be imported."""
    from roma_dspy.tools.crypto.arkham import BlockchainNetwork, AssetIdentifier

    assert BlockchainNetwork is not None
    assert AssetIdentifier is not None


def test_types_imports():
    """Test that Arkham-specific types can be imported."""
    from roma_dspy.tools.crypto.arkham import (
        TokenHolder,
        TokenFlow,
        Transfer,
        TokenBalance,
    )

    assert TokenHolder is not None
    assert TokenFlow is not None
    assert Transfer is not None
    assert TokenBalance is not None
