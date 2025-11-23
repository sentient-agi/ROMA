"""Currency and quote asset enums for crypto toolkits."""

from __future__ import annotations

from enum import Enum


class FiatCurrency(str, Enum):
    """Supported fiat currencies for crypto pricing."""

    USD = "usd"
    EUR = "eur"
    GBP = "gbp"
    JPY = "jpy"
    CNY = "cny"
    KRW = "krw"
    INR = "inr"
    AUD = "aud"
    CAD = "cad"
    CHF = "chf"
    RUB = "rub"
    BRL = "brl"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class CryptoCurrency(str, Enum):
    """Major cryptocurrencies used as quote currencies."""

    BTC = "btc"
    ETH = "eth"
    BNB = "bnb"
    USDT = "usdt"
    USDC = "usdc"
    DAI = "dai"
    BUSD = "busd"

    # Additional quote currencies
    ADA = "ada"
    DOT = "dot"
    SOL = "sol"
    MATIC = "matic"
    AVAX = "avax"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class QuoteCurrency(str, Enum):
    """Combined fiat and crypto quote currencies.

    This is a convenience enum that includes both fiat and crypto currencies
    for toolkits that support pricing in multiple types of quote assets.
    """

    # Fiat currencies
    USD = "usd"
    EUR = "eur"
    GBP = "gbp"
    JPY = "jpy"
    CNY = "cny"
    KRW = "krw"
    INR = "inr"

    # Crypto currencies
    BTC = "btc"
    ETH = "eth"
    BNB = "bnb"
    USDT = "usdt"
    USDC = "usdc"
    DAI = "dai"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value

    @property
    def is_fiat(self) -> bool:
        """Check if this is a fiat currency."""
        fiat_values = {e.value for e in FiatCurrency}
        return self.value in fiat_values

    @property
    def is_crypto(self) -> bool:
        """Check if this is a cryptocurrency."""
        crypto_values = {e.value for e in CryptoCurrency}
        return self.value in crypto_values
