"""Common value objects used across all crypto toolkits."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Any, Dict
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ResponseStatus(str, Enum):
    """Response status for toolkit operations."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"  # Some data succeeded, some failed


class ErrorType(str, Enum):
    """Standard error types across crypto toolkits."""

    VALIDATION_ERROR = "validation_error"
    API_ERROR = "api_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    NETWORK_ERROR = "network_error"
    NOT_FOUND_ERROR = "not_found_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN_ERROR = "unknown_error"


class BaseResponse(BaseModel):
    """Base response model for all crypto toolkit responses.

    All toolkit responses should inherit from this to ensure
    consistent response structure across different data sources.
    """

    success: bool = Field(description="Whether the operation was successful")
    message: Optional[str] = Field(
        None, description="Human-readable message (typically for errors)"
    )
    error_type: Optional[ErrorType] = Field(
        None, description="Type of error if success=False"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True


class PricePoint(BaseModel):
    """Single price data point.

    Generic price representation used across different crypto data sources.
    Can represent spot price, mark price, index price, etc.
    """

    price: Decimal = Field(description="Price value")
    timestamp: datetime = Field(description="Price timestamp")

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, v) -> Decimal:
        """Convert string/float prices to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class AssetIdentifier(BaseModel):
    """Generic asset/token identifier.

    Flexible identifier that can represent symbols (BTCUSDT),
    token IDs (bitcoin), or contract addresses depending on the data source.
    """

    symbol: Optional[str] = Field(None, description="Trading symbol (e.g., BTCUSDT)")
    token_id: Optional[str] = Field(
        None, description="Token identifier (e.g., bitcoin)"
    )
    contract_address: Optional[str] = Field(None, description="Smart contract address")
    chain: Optional[str] = Field(None, description="Blockchain network")
    name: Optional[str] = Field(None, description="Asset name")

    def __str__(self) -> str:
        """String representation prioritizes symbol, then token_id."""
        return self.symbol or self.token_id or self.contract_address or "unknown"


class Pagination(BaseModel):
    """Pagination metadata for large datasets."""

    page: int = Field(1, ge=1, description="Current page number")
    page_size: int = Field(100, ge=1, le=1000, description="Items per page")
    total_items: Optional[int] = Field(None, description="Total number of items")
    total_pages: Optional[int] = Field(None, description="Total number of pages")
    has_next: bool = Field(False, description="Whether there are more pages")
    has_prev: bool = Field(False, description="Whether there are previous pages")


class DataSource(BaseModel):
    """Metadata about the data source."""

    provider: str = Field(description="Data provider name (e.g., binance, coingecko)")
    endpoint: str = Field(description="API endpoint used")
    rate_limit: Optional[int] = Field(None, description="Requests per minute limit")
    cached: bool = Field(False, description="Whether response was cached")
