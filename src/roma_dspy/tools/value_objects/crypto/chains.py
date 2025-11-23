"""Blockchain network enums for crypto toolkits."""

from __future__ import annotations

from enum import Enum


class BlockchainNetwork(str, Enum):
    """Supported blockchain networks across crypto toolkits.

    This enum provides a standardized way to refer to blockchain networks
    across different crypto data sources (exchanges, DeFi protocols, analytics).
    """

    # EVM-compatible chains
    ETHEREUM = "ethereum"
    BINANCE_SMART_CHAIN = "bsc"
    POLYGON = "polygon"
    AVALANCHE = "avalanche"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"
    FANTOM = "fantom"

    # Non-EVM chains
    BITCOIN = "bitcoin"
    SOLANA = "solana"
    CARDANO = "cardano"
    POLKADOT = "polkadot"
    TRON = "tron"

    # Additional networks
    CRONOS = "cronos"
    GNOSIS = "gnosis"
    MOONBEAM = "moonbeam"
    AURORA = "aurora"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class EVMNetwork(str, Enum):
    """EVM-compatible blockchain networks only."""

    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    AVALANCHE = "avalanche"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"
    FANTOM = "fantom"
    CRONOS = "cronos"
    GNOSIS = "gnosis"
    MOONBEAM = "moonbeam"
    AURORA = "aurora"
