"""DefiLlama DeFi analytics toolkit for ROMA-DSPy.

Provides access to DefiLlama's DeFi analytics APIs for protocol analytics,
yield farming data, fees/revenue tracking, and ecosystem metrics.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer
from roma_dspy.tools.value_objects.crypto import BlockchainNetwork
from roma_dspy.tools.crypto.defillama.client import (
    DefiLlamaAPIClient,
    DefiLlamaAPIError,
)
from roma_dspy.tools.crypto.defillama.types import DataType


class DefiLlamaToolkit(BaseToolkit):
    """DefiLlama DeFi Analytics Toolkit.

    Provides comprehensive access to DefiLlama's DeFi analytics platform
    for protocol TVL tracking, fee analysis, yield farming opportunities,
    and ecosystem metrics across multiple blockchains.

    Features:
    - Protocol TVL and historical data
    - Daily fees and revenue analysis
    - Yield farming pools and APY data (Pro)
    - User activity metrics (Pro)
    - Cross-chain analytics
    - Statistical analysis of DeFi metrics

    Example:
        ```python
        from . import DefiLlamaToolkit

        # Basic usage (free API)
        toolkit = DefiLlamaToolkit()

        # Get protocol fees
        fees = await toolkit.get_protocol_fees("aave")

        # With storage for large responses (requires config)
        from roma_dspy.config.manager import ConfigManager
        from roma_dspy.core.storage import FileStorage

        config = ConfigManager().load_config()
        storage = FileStorage(
            config=config.storage,
            execution_id="my_execution"
        )
        toolkit = DefiLlamaToolkit(file_storage=storage)

        # Pro API features
        pro_toolkit = DefiLlamaToolkit(
            api_key="your_api_key",
            enable_pro_features=True
        )
        yields = await pro_toolkit.get_yield_pools()
        ```
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        enable_pro_features: bool = False,
        default_chain: str = "ethereum",
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        file_storage: Optional["FileStorage"] = None,
        enable_analysis: bool = True,
        **config,
    ):
        """Initialize DefiLlama toolkit.

        Args:
            api_key: DefiLlama Pro API key (reads from DEFILLAMA_API_KEY if None)
            enable_pro_features: Enable Pro API endpoints
            default_chain: Default blockchain for chain-specific queries
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include
            exclude_tools: Tools to exclude
            file_storage: Optional FileStorage for large data persistence
            enable_analysis: Whether to include statistical analysis in responses
            **config: Additional toolkit configuration (storage_threshold_kb, etc.)
        """
        # Set attributes BEFORE calling super().__init__() because
        # super().__init__() calls _register_all_tools() which calls _is_tool_available()
        # which needs these attributes to exist

        # API key configuration
        self.api_key = api_key or os.getenv("DEFILLAMA_API_KEY")
        self.enable_pro_features = enable_pro_features and bool(self.api_key)

        # Default chain
        self.default_chain = default_chain.lower()

        # Analysis configuration
        self.enable_analysis = enable_analysis
        self.stats = StatisticalAnalyzer() if enable_analysis else None

        # Now call parent init which will use _is_tool_available()
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            file_storage=file_storage,
            **config,
        )

        # Initialize API client
        self.client = DefiLlamaAPIClient(
            api_key=self.api_key,
            use_pro=self.enable_pro_features,
        )

        logger.info(
            f"Initialized DefiLlamaToolkit with default chain '{self.default_chain}', "
            f"Pro features: {self.enable_pro_features}, "
            f"Analysis: {self.enable_analysis}"
        )

    def _setup_dependencies(self) -> None:
        """Setup external dependencies."""
        # No external dependencies needed
        pass

    def _initialize_tools(self) -> None:
        """Initialize toolkit-specific configuration."""
        # Tool registration handled automatically by BaseToolkit
        pass

    def _is_tool_available(self, tool_name: str) -> bool:
        """Check if tool is available based on configuration.

        Pro API tools require API key to be available.
        """
        # Pro-only tools
        pro_tools = {
            "get_yield_pools",
            "get_yield_chart",
            "get_yield_pools_borrow",
            "get_yield_perps",
            "get_active_users",
            "get_chain_assets",
            "get_historical_liquidity",
        }

        if tool_name in pro_tools:
            return self.enable_pro_features

        return True

    def _validate_chain(self, chain: str) -> str:
        """Validate and normalize chain parameter.

        Args:
            chain: Chain identifier

        Returns:
            Normalized chain identifier

        Raises:
            ValueError: If chain format is invalid
        """
        chain = chain.strip().lower()
        if not chain:
            raise ValueError("Chain cannot be empty")

        # Basic validation - chains are lowercase identifiers
        if any(char in chain for char in [" ", "/", "\\", "?", "#"]):
            raise ValueError(f"Invalid chain format: {chain}")

        return chain

    def _validate_protocol(self, protocol: str) -> str:
        """Validate and normalize protocol parameter.

        Args:
            protocol: Protocol identifier

        Returns:
            Normalized protocol identifier

        Raises:
            ValueError: If protocol format is invalid
        """
        protocol = protocol.strip().lower()
        if not protocol:
            raise ValueError("Protocol cannot be empty")

        # Basic validation - protocols are lowercase with hyphens
        if any(char in protocol for char in [" ", "/", "\\", "?", "#"]):
            raise ValueError(f"Invalid protocol format: {protocol}")

        return protocol

    # =========================================================================
    # TVL & Protocol Tools
    # =========================================================================

    async def get_protocols(self) -> Dict[str, Any]:
        """Get all protocols with current TVL data.

        Retrieves comprehensive list of all DeFi protocols tracked by DefiLlama.

        Returns:
            dict: Protocols data or file path for large responses

        Example:
            ```python
            protocols = await toolkit.get_protocols()
            if protocols["success"]:
                for protocol in protocols["data"][:10]:
                    print(f"{protocol['name']}: ${protocol['tvl']:,.0f}")
            ```
        """
        try:
            data = await self.client.get_protocols()

            # Validate response
            if not isinstance(data, list):
                raise ValueError(f"Expected list response, got {type(data)}")

            # Calculate analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    # Extract TVL values for statistical analysis
                    tvl_values = []
                    categories = {}
                    chains_usage = {}

                    for protocol in data:
                        try:
                            if protocol.get("tvl") is not None:
                                tvl_values.append(float(protocol["tvl"]))

                            # Count by category
                            category = protocol.get("category", "Unknown")
                            categories[category] = categories.get(category, 0) + 1

                            # Count chain usage
                            protocol_chains = protocol.get("chains", [])
                            if isinstance(protocol_chains, list):
                                for chain in protocol_chains:
                                    chains_usage[chain] = chains_usage.get(chain, 0) + 1

                        except (ValueError, TypeError):
                            continue

                    if tvl_values:
                        # Statistical analysis
                        tvl_array = np.array(tvl_values)
                        tvl_distribution = self.stats.calculate_price_statistics(
                            tvl_array
                        )
                        total_tvl = sum(tvl_values)

                        # Market concentration
                        top_10_tvl = sum(sorted(tvl_values, reverse=True)[:10])
                        concentration_ratio = (
                            (top_10_tvl / total_tvl * 100) if total_tvl > 0 else 0
                        )

                        analysis = {
                            "ecosystem_overview": {
                                "total_protocols": len(data),
                                "total_tvl": total_tvl,
                                "market_concentration_top10_pct": round(
                                    concentration_ratio, 1
                                ),
                                "tvl_distribution": tvl_distribution,
                            },
                            "category_breakdown": dict(
                                sorted(
                                    categories.items(), key=lambda x: x[1], reverse=True
                                )[:10]
                            ),
                            "chain_adoption": dict(
                                sorted(
                                    chains_usage.items(),
                                    key=lambda x: x[1],
                                    reverse=True,
                                )[:10]
                            ),
                            "market_insights": {
                                "dominant_category": (
                                    max(categories.items(), key=lambda x: x[1])[0]
                                    if categories
                                    else None
                                ),
                                "most_adopted_chain": (
                                    max(chains_usage.items(), key=lambda x: x[1])[0]
                                    if chains_usage
                                    else None
                                ),
                                "concentration_level": (
                                    "high"
                                    if concentration_ratio > 50
                                    else "moderate"
                                    if concentration_ratio > 30
                                    else "distributed"
                                ),
                            },
                        }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate protocol analysis: {e}")

            # Use storage-enabled response builder
            response = await self._build_success_response(
                data=data,
                storage_data_type="protocols",
                storage_prefix="all_protocols",
                tool_name="get_protocols",
                count=len(data),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_protocols")
        except Exception as e:
            logger.error(f"Unexpected error in get_protocols: {e}")
            return self._build_error_response(e, tool_name="get_protocols")

    async def get_protocol_tvl(self, protocol: str) -> Dict[str, Any]:
        """Get current TVL for a specific protocol.

        Args:
            protocol: Protocol identifier (e.g., "aave", "uniswap")

        Returns:
            dict: Current TVL data

        Example:
            ```python
            aave_tvl = await toolkit.get_protocol_tvl("aave")
            print(f"Aave TVL: ${aave_tvl['tvl']:,.0f}")
            ```
        """
        try:
            protocol = self._validate_protocol(protocol)
            tvl_value = await self.client.get_protocol_tvl(protocol)

            # Validate response
            if not isinstance(tvl_value, (int, float)):
                raise ValueError(f"Expected numeric TVL value, got {type(tvl_value)}")

            # Format for readability
            if tvl_value >= 1e9:
                tvl_formatted = f"${tvl_value / 1e9:.2f}B"
            elif tvl_value >= 1e6:
                tvl_formatted = f"${tvl_value / 1e6:.2f}M"
            else:
                tvl_formatted = f"${tvl_value:,.2f}"

            return await self._build_success_response(
                data={
                    "protocol": protocol,
                    "tvl": float(tvl_value),
                    "tvl_formatted": tvl_formatted,
                },
                tool_name="get_protocol_tvl",
                protocol=protocol,
            )

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_protocol_tvl", protocol=protocol
            )

    async def get_protocol_detail(self, protocol: str) -> Dict[str, Any]:
        """Get detailed protocol information including historical TVL.

        Args:
            protocol: Protocol identifier

        Returns:
            dict: Detailed protocol data or file path for large responses

        Example:
            ```python
            detail = await toolkit.get_protocol_detail("uniswap")
            ```
        """
        try:
            protocol = self._validate_protocol(protocol)
            data = await self.client.get_protocol_detail(protocol)

            return await self._build_success_response(
                data=data,
                storage_data_type="protocol_detail",
                storage_prefix=f"{protocol}_detail",
                tool_name="get_protocol_detail",
                protocol=protocol,
            )

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_protocol_detail", protocol=protocol
            )

    async def get_chains(self) -> Dict[str, Any]:
        """Get current TVL for all blockchain networks.

        Returns:
            dict: Chains TVL data

        Example:
            ```python
            chains = await toolkit.get_chains()
            for chain in chains["data"][:5]:
                print(f"{chain['name']}: ${chain['tvl']:,.0f}")
            ```
        """
        try:
            data = await self.client.get_chains()

            return await self._build_success_response(
                data=data,
                storage_data_type="chains",
                storage_prefix="all_chains",
                tool_name="get_chains",
                count=len(data) if isinstance(data, list) else 1,
            )

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_chains")

    async def get_chain_historical_tvl(
        self, chain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get historical TVL data for a blockchain.

        Args:
            chain: Chain identifier (uses default_chain if None)

        Returns:
            dict: Historical TVL data or file path for large responses

        Example:
            ```python
            eth_tvl = await toolkit.get_chain_historical_tvl("ethereum")
            ```
        """
        try:
            chain = chain or self.default_chain
            chain = self._validate_chain(chain)

            data = await self.client.get_chain_historical_tvl(chain)

            # Calculate historical TVL analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and isinstance(data, list) and data:
                try:
                    # Extract TVL values from historical data
                    tvl_values = []
                    timestamps = []

                    for item in data:
                        try:
                            if isinstance(item, dict):
                                tvl = item.get("tvl")
                                timestamp = item.get("date")
                            elif isinstance(item, list) and len(item) >= 2:
                                timestamp = item[0]
                                tvl = item[1]
                            else:
                                continue

                            if tvl is not None:
                                tvl_values.append(float(tvl))
                                timestamps.append(timestamp)

                        except (ValueError, TypeError):
                            continue

                    if tvl_values and len(tvl_values) >= 2:
                        tvl_array = np.array(tvl_values)

                        # Current and historical metrics
                        current_tvl = tvl_values[-1]
                        ath_tvl = float(np.max(tvl_array))
                        atl_tvl = float(np.min(tvl_array))

                        # Growth calculations
                        growth_30d = 0
                        growth_90d = 0
                        if len(tvl_values) >= 30:
                            growth_30d = (
                                ((tvl_values[-1] / tvl_values[-30]) - 1) * 100
                                if tvl_values[-30] > 0
                                else 0
                            )
                        if len(tvl_values) >= 90:
                            growth_90d = (
                                ((tvl_values[-1] / tvl_values[-90]) - 1) * 100
                                if tvl_values[-90] > 0
                                else 0
                            )

                        # Trend analysis
                        trend_analysis = self.stats.analyze_price_trends(
                            tvl_array, window=min(30, len(tvl_values))
                        )

                        analysis = {
                            "tvl_metrics": {
                                "current_tvl": current_tvl,
                                "ath_tvl": ath_tvl,
                                "atl_tvl": atl_tvl,
                                "distance_from_ath_pct": round(
                                    ((current_tvl / ath_tvl) - 1) * 100, 2
                                ),
                            },
                            "growth_metrics": {
                                "growth_30d_pct": round(growth_30d, 2),
                                "growth_90d_pct": round(growth_90d, 2),
                                "trend_direction": trend_analysis.get(
                                    "trend_direction", "sideways"
                                ),
                                "momentum_pct": trend_analysis.get("momentum_pct", 0),
                            },
                            "health_indicators": {
                                "data_points": len(tvl_values),
                                "health_status": (
                                    "growing"
                                    if growth_30d > 5
                                    else "declining"
                                    if growth_30d < -5
                                    else "stable"
                                ),
                            },
                        }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate historical TVL analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="chain_historical_tvl",
                storage_prefix=f"{chain}_historical_tvl",
                tool_name="get_chain_historical_tvl",
                chain=chain,
                count=len(data) if isinstance(data, list) else 1,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_chain_historical_tvl", chain=chain
            )

    # =========================================================================
    # Fees & Revenue Tools
    # =========================================================================

    async def get_protocol_fees(
        self,
        protocol: str,
        data_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get daily fees and revenue data for a protocol.

        Args:
            protocol: Protocol identifier (e.g., "aave", "uniswap")
            data_type: Type of data ("dailyFees", "dailyRevenue", "dailyHoldersRevenue")

        Returns:
            dict: Protocol fees data or file path for large responses

        Example:
            ```python
            fees = await toolkit.get_protocol_fees("uniswap", "dailyFees")
            print(f"24h fees: ${fees['data']['total24h']:,.0f}")
            ```
        """
        try:
            protocol = self._validate_protocol(protocol)
            data = await self.client.get_protocol_fees(protocol, data_type)

            # Calculate fee analytics if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    # Extract key metrics
                    total_24h = data.get("total24h", 0)
                    total_7d = data.get("total7d", 0)
                    total_all_time = data.get("totalAllTime", 0)
                    change_1d = data.get("change_1d", 0)

                    # Historical data analysis if available
                    historical_data = data.get("totalDataChart", [])
                    if historical_data and len(historical_data) > 1:
                        # Extract values from chart data
                        values = [item[1] for item in historical_data]

                        if len(values) >= 2:
                            values_array = np.array(values)

                            # Trend analysis
                            trend_analysis = self.stats.analyze_price_trends(
                                values_array, window=min(30, len(values))
                            )

                            # Growth metrics
                            monthly_growth = 0
                            if len(values) >= 30:
                                monthly_growth = (
                                    ((values[-1] / values[-30]) - 1) * 100
                                    if values[-30] > 0
                                    else 0
                                )

                            analysis = {
                                "financial_metrics": {
                                    "daily_fees_24h": total_24h,
                                    "weekly_fees": total_7d,
                                    "all_time_fees": total_all_time,
                                    "daily_change_pct": change_1d,
                                    "weekly_run_rate": total_7d * 52.14,  # Annualized
                                    "fee_sustainability_score": (
                                        "high"
                                        if total_24h > 100000
                                        else "medium"
                                        if total_24h > 10000
                                        else "low"
                                    ),
                                },
                                "trend_analysis": {
                                    "trend_direction": trend_analysis.get(
                                        "trend_direction", "sideways"
                                    ),
                                    "momentum_pct": trend_analysis.get(
                                        "momentum_pct", 0
                                    ),
                                    "monthly_growth_pct": round(monthly_growth, 2),
                                    "volatility_regime": self.stats.classify_volatility_from_change(
                                        abs(change_1d)
                                    ).value,
                                },
                                "revenue_insights": {
                                    "avg_daily_revenue": total_7d / 7
                                    if total_7d > 0
                                    else 0,
                                    "revenue_consistency": (
                                        "stable" if abs(change_1d) < 10 else "volatile"
                                    ),
                                    "growth_stage": (
                                        "mature"
                                        if total_all_time > 1000000
                                        else "emerging"
                                    ),
                                },
                            }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate fee analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="protocol_fees",
                storage_prefix=f"{protocol}_fees_{data_type or 'dailyFees'}",
                tool_name="get_protocol_fees",
                protocol=protocol,
                data_type=data_type or "dailyFees",
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_protocol_fees", protocol=protocol
            )

    async def get_chain_fees(
        self,
        chain: Optional[str] = None,
        data_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get overview of daily fees for a blockchain.

        Args:
            chain: Chain identifier (uses default_chain if None)
            data_type: Type of data

        Returns:
            dict: Chain fees data or file path for large responses

        Example:
            ```python
            eth_fees = await toolkit.get_chain_fees("ethereum")
            ```
        """
        try:
            chain = chain or self.default_chain
            chain = self._validate_chain(chain)

            data = await self.client.get_chain_fees(chain, data_type)

            # Calculate chain fee analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    # Handle both dict and list responses
                    protocols_data = (
                        data.get("protocols", []) if isinstance(data, dict) else []
                    )

                    if protocols_data:
                        # Extract protocol fees
                        protocol_fees = []
                        for proto in protocols_data:
                            try:
                                total_24h = proto.get("total24h", 0)
                                if total_24h and total_24h > 0:
                                    protocol_fees.append(
                                        {
                                            "name": proto.get("name"),
                                            "fees": float(total_24h),
                                        }
                                    )
                            except (ValueError, TypeError):
                                continue

                        if protocol_fees:
                            # Sort by fees
                            protocol_fees.sort(key=lambda x: x["fees"], reverse=True)
                            total_fees = sum(p["fees"] for p in protocol_fees)
                            top_5_fees = sum(p["fees"] for p in protocol_fees[:5])

                            analysis = {
                                "fee_overview": {
                                    "total_protocols": len(protocol_fees),
                                    "total_fees_24h": total_fees,
                                    "top_5_concentration_pct": round(
                                        (top_5_fees / total_fees * 100), 2
                                    )
                                    if total_fees > 0
                                    else 0,
                                },
                                "top_protocols": [
                                    {"name": p["name"], "fees_24h": p["fees"]}
                                    for p in protocol_fees[:5]
                                ],
                                "market_insights": {
                                    "competition_level": "high"
                                    if len(protocol_fees) > 20
                                    else "moderate"
                                    if len(protocol_fees) > 10
                                    else "low",
                                    "market_leader": protocol_fees[0]["name"]
                                    if protocol_fees
                                    else None,
                                },
                            }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate chain fee analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="chain_fees",
                storage_prefix=f"{chain}_fees_{data_type or 'dailyFees'}",
                tool_name="get_chain_fees",
                chain=chain,
                data_type=data_type or "dailyFees",
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_chain_fees", chain=chain
            )

    # =========================================================================
    # Pro API Tools
    # =========================================================================

    async def get_yield_pools(self) -> Dict[str, Any]:
        """Get all yield farming pools with current APY data (Pro API).

        Returns:
            dict: Yield pools data or file path for large responses

        Example:
            ```python
            pools = await toolkit.get_yield_pools()
            ```
        """
        try:
            data = await self.client.get_yield_pools()

            # Handle different response formats
            pools_data = data.get("data", data) if isinstance(data, dict) else data

            # Calculate yield analysis if enabled
            analysis = {}
            if (
                self.enable_analysis
                and self.stats
                and isinstance(pools_data, list)
                and pools_data
            ):
                try:
                    # Extract APY values
                    apy_values = []
                    chains_count = {}
                    protocols_count = {}

                    for pool in pools_data:
                        try:
                            apy = pool.get("apy")
                            if apy is not None and apy > 0:
                                apy_values.append(float(apy))

                            chain = pool.get("chain")
                            if chain:
                                chains_count[chain] = chains_count.get(chain, 0) + 1

                            project = pool.get("project")
                            if project:
                                protocols_count[project] = (
                                    protocols_count.get(project, 0) + 1
                                )

                        except (ValueError, TypeError):
                            continue

                    if apy_values:
                        apy_array = np.array(apy_values)
                        avg_apy = float(np.mean(apy_array))
                        median_apy = float(np.median(apy_array))
                        max_apy = float(np.max(apy_array))

                        # Categorize pools by yield
                        high_yield = sum(1 for apy in apy_values if apy > 20)
                        medium_yield = sum(1 for apy in apy_values if 5 <= apy <= 20)
                        stable_yield = sum(1 for apy in apy_values if apy < 5)

                        analysis = {
                            "yield_landscape": {
                                "total_pools": len(pools_data),
                                "avg_apy": round(avg_apy, 2),
                                "median_apy": round(median_apy, 2),
                                "max_apy": round(max_apy, 2),
                            },
                            "opportunity_segments": {
                                "high_yield_pools": high_yield,  # >20% APY
                                "medium_yield_pools": medium_yield,  # 5-20%
                                "stable_yield_pools": stable_yield,  # <5%
                                "risk_reward_ratio": round(
                                    high_yield / len(apy_values), 3
                                ),
                            },
                            "ecosystem_diversity": {
                                "active_chains": len(chains_count),
                                "active_protocols": len(protocols_count),
                                "top_chains": dict(
                                    sorted(
                                        chains_count.items(),
                                        key=lambda x: x[1],
                                        reverse=True,
                                    )[:5]
                                ),
                                "top_protocols": dict(
                                    sorted(
                                        protocols_count.items(),
                                        key=lambda x: x[1],
                                        reverse=True,
                                    )[:5]
                                ),
                            },
                        }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate yield analysis: {e}")

            response = await self._build_success_response(
                data=pools_data,
                storage_data_type="yield_pools",
                storage_prefix="all_yield_pools",
                tool_name="get_yield_pools",
                count=len(pools_data) if isinstance(pools_data, list) else 1,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_yield_pools")

    async def get_yield_chart(self, pool_id: str) -> Dict[str, Any]:
        """Get historical yield chart data for a pool (Pro API).

        Args:
            pool_id: Pool identifier

        Returns:
            dict: Historical yield data or file path for large responses
        """
        try:
            if not pool_id:
                raise ValueError("Pool ID is required")

            data = await self.client.get_yield_chart(pool_id)

            # Calculate yield volatility analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    # Extract APY values from chart data
                    apy_values = []
                    if isinstance(data, dict) and "data" in data:
                        chart_data = data.get("data", [])
                    elif isinstance(data, list):
                        chart_data = data
                    else:
                        chart_data = []

                    for item in chart_data:
                        try:
                            apy = item.get("apy") if isinstance(item, dict) else None
                            if apy is not None and apy > 0:
                                apy_values.append(float(apy))
                        except (ValueError, TypeError):
                            continue

                    if apy_values and len(apy_values) >= 2:
                        apy_array = np.array(apy_values)
                        avg_apy = float(np.mean(apy_array))
                        std_apy = float(np.std(apy_array))
                        current_apy = apy_values[-1]

                        # Volatility classification
                        volatility_pct = (std_apy / avg_apy * 100) if avg_apy > 0 else 0

                        analysis = {
                            "yield_metrics": {
                                "current_apy": round(current_apy, 2),
                                "avg_apy": round(avg_apy, 2),
                                "min_apy": round(float(np.min(apy_array)), 2),
                                "max_apy": round(float(np.max(apy_array)), 2),
                            },
                            "risk_metrics": {
                                "volatility_pct": round(volatility_pct, 2),
                                "volatility_category": (
                                    "high"
                                    if volatility_pct > 30
                                    else "moderate"
                                    if volatility_pct > 15
                                    else "low"
                                ),
                                "stability_score": max(0, 100 - volatility_pct),
                            },
                            "yield_insights": {
                                "data_points": len(apy_values),
                                "yield_trend": (
                                    "improving"
                                    if current_apy > avg_apy * 1.1
                                    else "declining"
                                    if current_apy < avg_apy * 0.9
                                    else "stable"
                                ),
                            },
                        }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate yield chart analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="yield_chart",
                storage_prefix=f"pool_{pool_id}_chart",
                tool_name="get_yield_chart",
                pool_id=pool_id,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_yield_chart", pool_id=pool_id
            )

    async def get_yield_pools_borrow(self) -> Dict[str, Any]:
        """Get borrow costs APY of assets from lending markets (Pro API).

        Returns:
            dict: Borrow costs data or file path for large responses
        """
        try:
            data = await self.client.get_yield_pools_borrow()

            # Calculate borrow rate analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    borrow_data = (
                        data.get("data", data) if isinstance(data, dict) else data
                    )
                    if isinstance(borrow_data, list) and borrow_data:
                        # Extract borrow APY values
                        borrow_rates = []
                        for item in borrow_data:
                            try:
                                apy_borrow = item.get("apyBorrow") or item.get("apy")
                                if apy_borrow is not None and apy_borrow > 0:
                                    borrow_rates.append(float(apy_borrow))
                            except (ValueError, TypeError):
                                continue

                        if borrow_rates:
                            rates_array = np.array(borrow_rates)
                            avg_rate = float(np.mean(rates_array))

                            # Categorize rates
                            low_cost = sum(1 for r in borrow_rates if r < 5)
                            medium_cost = sum(1 for r in borrow_rates if 5 <= r <= 15)
                            high_cost = sum(1 for r in borrow_rates if r > 15)

                            analysis = {
                                "borrow_rate_overview": {
                                    "total_pools": len(borrow_rates),
                                    "avg_borrow_rate": round(avg_rate, 2),
                                    "min_borrow_rate": round(
                                        float(np.min(rates_array)), 2
                                    ),
                                    "max_borrow_rate": round(
                                        float(np.max(rates_array)), 2
                                    ),
                                },
                                "cost_distribution": {
                                    "low_cost_pools": low_cost,  # <5%
                                    "medium_cost_pools": medium_cost,  # 5-15%
                                    "high_cost_pools": high_cost,  # >15%
                                },
                                "market_conditions": {
                                    "borrowing_affordability": "cheap"
                                    if avg_rate < 5
                                    else "moderate"
                                    if avg_rate < 10
                                    else "expensive",
                                },
                            }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate borrow rate analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="borrow_yields",
                storage_prefix="borrow_costs",
                tool_name="get_yield_pools_borrow",
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_yield_pools_borrow")

    async def get_yield_perps(self) -> Dict[str, Any]:
        """Get funding rates and open interest of perps (Pro API).

        Returns:
            dict: Perpetuals data or file path for large responses
        """
        try:
            data = await self.client.get_yield_perps()

            # Calculate perps market analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    perps_data = (
                        data.get("data", data) if isinstance(data, dict) else data
                    )
                    if isinstance(perps_data, list) and perps_data:
                        # Extract funding rates
                        funding_rates = []
                        open_interests = []

                        for item in perps_data:
                            try:
                                funding_rate = item.get("fundingRate") or item.get(
                                    "apy"
                                )
                                if funding_rate is not None:
                                    funding_rates.append(float(funding_rate))

                                oi = item.get("openInterest")
                                if oi is not None and oi > 0:
                                    open_interests.append(float(oi))
                            except (ValueError, TypeError):
                                continue

                        if funding_rates:
                            rates_array = np.array(funding_rates)
                            avg_funding = float(np.mean(rates_array))

                            # Market sentiment based on funding rates
                            positive_funding = sum(1 for r in funding_rates if r > 0)
                            negative_funding = sum(1 for r in funding_rates if r < 0)

                            analysis = {
                                "funding_rate_overview": {
                                    "avg_funding_rate": round(avg_funding, 4),
                                    "min_funding_rate": round(
                                        float(np.min(rates_array)), 4
                                    ),
                                    "max_funding_rate": round(
                                        float(np.max(rates_array)), 4
                                    ),
                                },
                                "market_sentiment": {
                                    "positive_funding_count": positive_funding,
                                    "negative_funding_count": negative_funding,
                                    "sentiment": "bullish"
                                    if positive_funding > negative_funding
                                    else "bearish"
                                    if negative_funding > positive_funding
                                    else "neutral",
                                },
                            }

                            if open_interests:
                                total_oi = sum(open_interests)
                                analysis["open_interest"] = {
                                    "total_open_interest": total_oi,
                                    "avg_open_interest": round(
                                        total_oi / len(open_interests), 2
                                    ),
                                }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate perps analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="perps_data",
                storage_prefix="perps_funding",
                tool_name="get_yield_perps",
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_yield_perps")

    async def get_active_users(self) -> Dict[str, Any]:
        """Get active user metrics for all protocols (Pro API).

        Returns:
            dict: Active users data

        Example:
            ```python
            users = await toolkit.get_active_users()
            ```
        """
        try:
            data = await self.client.get_active_users()

            # Calculate user activity analysis if enabled
            analysis = {}
            if self.enable_analysis and self.stats and data:
                try:
                    protocols_data = (
                        data if isinstance(data, list) else data.get("protocols", [])
                    )
                    if protocols_data:
                        # Extract user counts
                        user_counts = []
                        protocol_names = []

                        for proto in protocols_data:
                            try:
                                users = proto.get("activeUsers") or proto.get("users")
                                if users and users > 0:
                                    user_counts.append(int(users))
                                    protocol_names.append(proto.get("name", "Unknown"))
                            except (ValueError, TypeError):
                                continue

                        if user_counts:
                            # Sort protocols by users
                            protocol_users = sorted(
                                zip(protocol_names, user_counts),
                                key=lambda x: x[1],
                                reverse=True,
                            )

                            total_users = sum(user_counts)
                            users_array = np.array(user_counts)

                            analysis = {
                                "user_metrics": {
                                    "total_protocols": len(user_counts),
                                    "total_active_users": total_users,
                                    "avg_users_per_protocol": round(
                                        float(np.mean(users_array)), 0
                                    ),
                                },
                                "top_protocols_by_users": [
                                    {"name": name, "users": users}
                                    for name, users in protocol_users[:5]
                                ],
                                "user_distribution": {
                                    "min_users": int(np.min(users_array)),
                                    "max_users": int(np.max(users_array)),
                                    "median_users": int(np.median(users_array)),
                                },
                            }

                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to calculate user activity analysis: {e}")

            response = await self._build_success_response(
                data=data,
                storage_data_type="active_users",
                storage_prefix="active_users",
                tool_name="get_active_users",
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_active_users")

    async def get_chain_assets(self) -> Dict[str, Any]:
        """Get asset breakdown across all blockchain networks (Pro API).

        Returns:
            dict: Chain assets data

        Example:
            ```python
            assets = await toolkit.get_chain_assets()
            ```
        """
        try:
            data = await self.client.get_chain_assets()

            return await self._build_success_response(
                data=data,
                storage_data_type="chain_assets",
                storage_prefix="chain_assets",
                tool_name="get_chain_assets",
            )

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_chain_assets")

    async def get_historical_liquidity(self, token: str) -> Dict[str, Any]:
        """Get historical liquidity data for a token (Pro API).

        Args:
            token: Token slug (e.g., "usdt", "usdc", "dai")

        Returns:
            dict: Historical liquidity data or file path for large responses

        Example:
            ```python
            liquidity = await toolkit.get_historical_liquidity("usdt")
            ```
        """
        try:
            token = token.strip().lower()
            if not token or len(token) < 2:
                raise ValueError("Token slug must be at least 2 characters")

            data = await self.client.get_historical_liquidity(token)

            return await self._build_success_response(
                data=data,
                storage_data_type="historical_liquidity",
                storage_prefix=f"{token}_liquidity",
                tool_name="get_historical_liquidity",
                token=token,
            )

        except (DefiLlamaAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_historical_liquidity", token=token
            )

    async def __aenter__(self) -> "DefiLlamaToolkit":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close toolkit and clean up resources."""
        await self.client.close()
        logger.debug("Closed DefiLlamaToolkit")
