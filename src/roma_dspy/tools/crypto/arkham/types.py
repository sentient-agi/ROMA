"""Arkham Intelligence blockchain analytics types.

This module contains ONLY Arkham-specific Pydantic models.
Shared value objects (BlockchainNetwork, AssetIdentifier, ErrorType, etc.)
are imported from tools/value_objects/crypto.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from roma_dspy.tools.value_objects.crypto import (
    AssetIdentifier,
    ErrorType,
)


class TokenHolder(BaseModel):
    """Token holder information with entity attribution.

    Represents a single token holder with balance and optional
    entity identification from Arkham's ULTRA AI engine.
    """

    address: str = Field(description="Wallet address")
    balance: Decimal = Field(description="Token balance (raw or formatted)")
    balance_usd: Optional[Decimal] = Field(None, description="USD value of balance")
    percentage: Optional[Decimal] = Field(
        None, description="Percentage of total supply"
    )
    entity_name: Optional[str] = Field(
        None, description="Entity name from Arkham ULTRA AI"
    )
    entity_type: Optional[str] = Field(
        None, description="Entity type (exchange, whale, fund, etc.)"
    )
    rank: Optional[int] = Field(None, description="Rank by balance size")

    @field_validator("balance", "balance_usd", "percentage", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Optional[Decimal]:
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class TokenFlow(BaseModel):
    """Token flow data for inflow/outflow analysis.

    Represents token movement data for a specific address,
    including inflows, outflows, and net flow calculations.
    """

    address: str = Field(description="Address with token flow")
    inflow_usd: Decimal = Field(description="Total inflow in USD")
    outflow_usd: Decimal = Field(description="Total outflow in USD")
    net_flow_usd: Decimal = Field(description="Net flow (inflow - outflow) in USD")
    timestamp: datetime = Field(description="Flow timestamp")
    entity_name: Optional[str] = Field(None, description="Entity name if known")

    @field_validator("inflow_usd", "outflow_usd", "net_flow_usd", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Decimal:
        """Convert numeric values to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class Transfer(BaseModel):
    """Blockchain transfer with entity attribution.

    Represents a single blockchain transaction transfer with
    optional entity mapping for sender and receiver.
    """

    from_address: str = Field(description="Sender address")
    to_address: str = Field(description="Receiver address")
    token: AssetIdentifier = Field(description="Token being transferred")
    value: Decimal = Field(description="Transfer amount (raw or formatted)")
    value_usd: Decimal = Field(description="USD value at time of transfer")
    timestamp: datetime = Field(description="Transfer timestamp")
    transaction_hash: str = Field(description="Transaction hash")
    from_entity: Optional[str] = Field(None, description="Sender entity name")
    to_entity: Optional[str] = Field(None, description="Receiver entity name")

    @field_validator("value", "value_usd", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Decimal:
        """Convert numeric values to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class TokenBalance(BaseModel):
    """Token balance for a wallet address.

    Represents a single token balance in a wallet portfolio,
    including USD value and chain information.
    """

    token: AssetIdentifier = Field(description="Token identifier")
    balance: Decimal = Field(description="Token balance")
    balance_usd: Decimal = Field(description="USD value of balance")
    chain: str = Field(description="Blockchain network")
    last_updated: datetime = Field(description="Last update timestamp")

    @field_validator("balance", "balance_usd", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Decimal:
        """Convert numeric values to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class ArkhamAPIError(Exception):
    """Exception raised when Arkham API returns an error.

    Uses ErrorType enum from value_objects/crypto for standardized
    error classification across all toolkits.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_type: ErrorType = ErrorType.API_ERROR,
    ):
        """Initialize Arkham API error.

        Args:
            message: Human-readable error message
            status_code: HTTP status code if applicable
            error_type: Standardized error type from ErrorType enum
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type

    def __str__(self) -> str:
        """String representation of error."""
        if self.status_code:
            return f"[{self.error_type.value}] HTTP {self.status_code}: {self.message}"
        return f"[{self.error_type.value}] {self.message}"
