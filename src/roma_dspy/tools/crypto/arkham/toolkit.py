"""Arkham Intelligence blockchain analytics toolkit.

Comprehensive toolkit for on-chain intelligence, token analysis, and wallet tracking
using Arkham Intelligence APIs with statistical analysis and storage integration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np
from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer
from roma_dspy.tools.value_objects.crypto import BlockchainNetwork, ErrorType
from roma_dspy.tools.crypto.arkham.client import ArkhamAPIClient, ArkhamAPIError

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage

__all__ = ["ArkhamToolkit"]


class ArkhamToolkit(BaseToolkit):
    """Arkham Intelligence blockchain analytics toolkit.

    Provides access to Arkham Intelligence APIs for on-chain data analysis,
    token holder tracking, transfer monitoring, and wallet portfolio analysis.

    Features:
        - Token analytics (top tokens, holders, flows)
        - Transfer tracking with entity attribution
        - Wallet balance monitoring across chains
        - Statistical analysis of distributions and concentrations
        - Automatic Parquet storage for large datasets
        - Rate limiting (20 req/sec standard, 1 req/sec heavy)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_chain: str = "ethereum",
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        file_storage: Optional["FileStorage"] = None,
        enable_analysis: bool = True,
        **config,
    ):
        """Initialize Arkham toolkit.

        Args:
            api_key: Arkham API key (reads from ARKHAM_API_KEY if None)
            default_chain: Default blockchain for queries
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include
            exclude_tools: Tools to exclude
            file_storage: Optional FileStorage for large data
            enable_analysis: Enable statistical analysis
            **config: Additional configuration
        """
        # Set attributes before super().__init__() for _is_tool_available
        self.api_key = api_key or os.getenv("ARKHAM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Arkham API key required. Set ARKHAM_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.default_chain = default_chain.lower()
        self.enable_analysis = enable_analysis
        self.stats = StatisticalAnalyzer() if enable_analysis else None

        # Initialize parent
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            file_storage=file_storage,
            **config,
        )

        # Initialize API client
        self.client = ArkhamAPIClient(api_key=self.api_key)

        logger.info(
            f"Initialized ArkhamToolkit with default chain '{self.default_chain}', "
            f"Analysis: {self.enable_analysis}"
        )

    def _setup_dependencies(self) -> None:
        """Setup external dependencies."""
        pass

    def _initialize_tools(self) -> None:
        """Initialize toolkit-specific configuration."""
        pass

    def _validate_chain(self, chain: str) -> str:
        """Validate chain using BlockchainNetwork enum.

        Args:
            chain: Chain identifier

        Returns:
            str: Normalized chain identifier

        Raises:
            ValueError: If chain not supported
        """
        chain_lower = chain.lower()

        # Check if chain exists in BlockchainNetwork
        try:
            # Try to find matching enum member
            for network in BlockchainNetwork:
                if network.value == chain_lower:
                    return chain_lower

            raise ValueError(
                f"Unsupported chain '{chain}'. Supported chains: "
                f"{[n.value for n in BlockchainNetwork]}"
            )
        except Exception as e:
            raise ValueError(f"Chain validation failed: {e}")

    def _validate_address(self, address: str) -> str:
        """Validate blockchain address format.

        Args:
            address: Address to validate

        Returns:
            str: Normalized address

        Raises:
            ValueError: If address invalid
        """
        if not address or not isinstance(address, str):
            raise ValueError("Address must be a non-empty string")

        address = address.strip()
        if not address:
            raise ValueError("Address cannot be empty")

        # Ethereum-style validation
        if address.startswith("0x") and len(address) == 42:
            try:
                int(address[2:], 16)
                return address.lower()
            except ValueError:
                raise ValueError(f"Invalid Ethereum address: {address}")

        # Bitcoin-style validation (basic length check)
        elif 26 <= len(address) <= 35:
            return address

        # Allow other formats with warning
        logger.warning(f"Address format not recognized: {address}")
        return address

    async def get_top_tokens(
        self,
        timeframe: str = "24h",
        order_by_agg: str = "volume",
        order_by_desc: bool = True,
        order_by_percent: bool = False,
        from_index: int = 0,
        size: int = 10,
        chains: Optional[str] = None,
        min_volume: Optional[float] = None,
        max_volume: Optional[float] = None,
        min_market_cap: Optional[float] = None,
        max_market_cap: Optional[float] = None,
        num_reference_periods: str = "auto",
        token_ids: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get top tokens by various metrics.

        Args:
            timeframe: Time period ("1h", "6h", "12h", "24h", "7d")
            order_by_agg: Metric to sort by
            order_by_desc: Sort descending
            order_by_percent: Sort by percentage change
            from_index: Pagination offset
            size: Number of results
            chains: Comma-separated chain list
            min_volume: Minimum volume filter
            max_volume: Maximum volume filter
            min_market_cap: Minimum market cap filter
            max_market_cap: Maximum market cap filter
            num_reference_periods: Reference periods for comparison
            token_ids: Comma-separated token IDs

        Returns:
            dict: Token data or file path for large responses
        """
        try:
            data = await self.client.get_top_tokens(
                timeframe=timeframe,
                order_by_agg=order_by_agg,
                order_by_desc=order_by_desc,
                order_by_percent=order_by_percent,
                from_index=from_index,
                size=size,
                chains=chains,
                min_volume=min_volume,
                max_volume=max_volume,
                min_market_cap=min_market_cap,
                max_market_cap=max_market_cap,
                num_reference_periods=num_reference_periods,
                token_ids=token_ids,
            )

            # Parse response
            if isinstance(data, dict) and "tokens" in data:
                tokens_list = data["tokens"] or []
                total_count = data.get("total", len(tokens_list))
            elif isinstance(data, list):
                tokens_list = data or []
                total_count = len(tokens_list)
            else:
                tokens_list = []
                total_count = 0

            # Analysis
            analysis = {}
            if self.enable_analysis and self.stats and tokens_list:
                try:
                    market_caps = []
                    volumes = []

                    for token in tokens_list:
                        token_info = token.get("token", {})
                        current_data = token.get("current", {})

                        if token_info.get("marketCap"):
                            market_caps.append(float(token_info["marketCap"]))

                        # Sum volume fields
                        vol_fields = [
                            "inflowDexVolume",
                            "outflowDexVolume",
                            "inflowCexVolume",
                            "outflowCexVolume",
                        ]
                        total_vol = sum(
                            float(current_data.get(f, 0))
                            for f in vol_fields
                            if current_data.get(f)
                        )
                        if total_vol > 0:
                            volumes.append(total_vol)

                    if market_caps:
                        mcap_array = np.array(market_caps)
                        mcap_stats = self.stats.calculate_price_statistics(mcap_array)
                        total_mcap = sum(market_caps)

                        analysis["market_cap_analysis"] = {
                            "total_market_cap": total_mcap,
                            "distribution": mcap_stats,
                            "top_token_dominance_pct": (
                                max(market_caps) / total_mcap * 100
                            )
                            if total_mcap > 0
                            else 0,
                        }

                    if volumes:
                        vol_array = np.array(volumes)
                        vol_stats = self.stats.calculate_price_statistics(vol_array)

                        analysis["volume_analysis"] = {
                            "total_volume": sum(volumes),
                            "distribution": vol_stats,
                        }

                except Exception as e:
                    logger.warning(f"Failed to calculate analysis: {e}")

            response = await self._build_success_response(
                data=tokens_list,
                storage_data_type="top_tokens",
                storage_prefix=f"{timeframe}_{order_by_agg}",
                tool_name="get_top_tokens",
                count=len(tokens_list),
                total=total_count,
                timeframe=timeframe,
                order_by_agg=order_by_agg,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except ArkhamAPIError as e:
            return self._build_error_response(e, tool_name="get_top_tokens")
        except Exception as e:
            logger.error(f"Unexpected error in get_top_tokens: {e}")
            return self._build_error_response(e, tool_name="get_top_tokens")

    async def get_token_holders(
        self,
        pricing_id: str,
        group_by_entity: bool = False,
    ) -> Dict[str, Any]:
        """Get token holder distribution.

        Args:
            pricing_id: CoinGecko pricing ID
            group_by_entity: Group by entity

        Returns:
            dict: Holder data or file path
        """
        try:
            data = await self.client.get_token_holders(
                pricing_id=pricing_id,
                group_by_entity=group_by_entity,
            )

            # Parse holders
            holders_list = []
            if isinstance(data, dict):
                if "addressTopHolders" in data:
                    addr_holders = data["addressTopHolders"]
                    if isinstance(addr_holders, list):
                        holders_list.extend(addr_holders)
                if "entityTopHolders" in data:
                    entity_holders = data["entityTopHolders"]
                    if isinstance(entity_holders, list):
                        holders_list.extend(entity_holders)
                if "holders" in data:
                    holders_dict = data["holders"]
                    if isinstance(holders_dict, dict):
                        for chain_holders in holders_dict.values():
                            if isinstance(chain_holders, list):
                                holders_list.extend(chain_holders)
            elif isinstance(data, list):
                holders_list = data

            # Analysis
            analysis = {}
            if self.enable_analysis and self.stats and holders_list:
                try:
                    balances = []
                    percentages = []

                    for holder in holders_list:
                        balance_fields = ["balance", "balanceExact", "amount", "usd"]
                        for field in balance_fields:
                            if field in holder and holder[field] is not None:
                                balances.append(float(holder[field]))
                                break

                        pct_fields = ["pctOfCap", "percentage", "percent"]
                        for field in pct_fields:
                            if field in holder and holder[field] is not None:
                                percentages.append(float(holder[field]))
                                break

                    if percentages:
                        top_10_pct = (
                            sum(percentages[:10])
                            if len(percentages) >= 10
                            else sum(percentages)
                        )
                        whale_count = sum(1 for p in percentages if p >= 1.0)

                        analysis = {
                            "concentration_metrics": {
                                "top_10_concentration_pct": round(top_10_pct, 2),
                                "whale_holders": whale_count,
                                "distribution_level": (
                                    "highly_concentrated"
                                    if top_10_pct > 80
                                    else "concentrated"
                                    if top_10_pct > 50
                                    else "moderate"
                                    if top_10_pct > 25
                                    else "distributed"
                                ),
                            }
                        }

                except Exception as e:
                    logger.warning(f"Failed to calculate holder analysis: {e}")

            response = await self._build_success_response(
                data=holders_list,
                storage_data_type="token_holders",
                storage_prefix=pricing_id,
                tool_name="get_token_holders",
                pricing_id=pricing_id,
                count=len(holders_list),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except ArkhamAPIError as e:
            return self._build_error_response(
                e, tool_name="get_token_holders", pricing_id=pricing_id
            )
        except Exception as e:
            logger.error(f"Unexpected error in get_token_holders: {e}")
            return self._build_error_response(e, tool_name="get_token_holders")

    async def get_token_top_flow(
        self,
        pricing_id: str,
        time_last: str = "24h",
        chains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get top token flows.

        Args:
            pricing_id: CoinGecko pricing ID
            time_last: Time period
            chains: Optional chain filter

        Returns:
            dict: Flow data or file path
        """
        try:
            data = await self.client.get_token_top_flow(
                pricing_id=pricing_id,
                time_last=time_last,
                chains=chains,
            )

            # Parse flows
            if isinstance(data, list):
                flows_list = data
            elif isinstance(data, dict):
                flows_list = data.get("flows", [data] if data else [])
            else:
                flows_list = []

            # Analysis
            analysis = {}
            if self.enable_analysis and flows_list:
                try:
                    in_usd = []
                    out_usd = []

                    for flow in flows_list:
                        if flow.get("inUSD") is not None:
                            in_usd.append(float(flow["inUSD"]))
                        if flow.get("outUSD") is not None:
                            out_usd.append(float(flow["outUSD"]))

                    total_in = sum(in_usd)
                    total_out = sum(out_usd)
                    net_flow = total_in - total_out

                    analysis = {
                        "flow_summary": {
                            "total_inflow_usd": round(total_in, 2),
                            "total_outflow_usd": round(total_out, 2),
                            "net_flow_usd": round(net_flow, 2),
                            "flow_direction": "net_inflow"
                            if net_flow > 0
                            else "net_outflow"
                            if net_flow < 0
                            else "balanced",
                        }
                    }

                except Exception as e:
                    logger.warning(f"Failed to calculate flow analysis: {e}")

            response = await self._build_success_response(
                data=flows_list,
                storage_data_type="token_flows",
                storage_prefix=f"{pricing_id}_{time_last}",
                tool_name="get_token_top_flow",
                pricing_id=pricing_id,
                count=len(flows_list),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except ArkhamAPIError as e:
            return self._build_error_response(e, tool_name="get_token_top_flow")
        except Exception as e:
            logger.error(f"Unexpected error in get_token_top_flow: {e}")
            return self._build_error_response(e, tool_name="get_token_top_flow")

    async def get_supported_chains(self) -> Dict[str, Any]:
        """Get supported blockchain networks.

        Returns:
            dict: Supported chains data
        """
        try:
            data = await self.client.get_supported_chains()

            if isinstance(data, dict) and "chains" in data:
                chains_list = data["chains"]
            elif isinstance(data, list):
                chains_list = data
            else:
                chains_list = []

            return await self._build_success_response(
                data=chains_list,
                tool_name="get_supported_chains",
                count=len(chains_list),
            )

        except ArkhamAPIError as e:
            return self._build_error_response(e, tool_name="get_supported_chains")
        except Exception as e:
            logger.error(f"Unexpected error in get_supported_chains: {e}")
            return self._build_error_response(e, tool_name="get_supported_chains")

    async def get_transfers(
        self,
        base: Optional[str] = None,
        chains: Optional[str] = None,
        flow: Optional[str] = None,
        from_addresses: Optional[str] = None,
        to_addresses: Optional[str] = None,
        tokens: Optional[str] = None,
        counterparties: Optional[str] = None,
        time_last: Optional[str] = None,
        time_gte: Optional[str] = None,
        time_lte: Optional[str] = None,
        value_gte: Optional[float] = None,
        value_lte: Optional[float] = None,
        usd_gte: Optional[float] = None,
        usd_lte: Optional[float] = None,
        sort_key: Optional[str] = None,
        sort_dir: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get transfers with filtering.

        Args:
            base: Filter by entity/address
            chains: Chain filter
            flow: Direction filter
            from_addresses: Comma-separated sender addresses/entities
            to_addresses: Comma-separated receiver addresses/entities
            tokens: Comma-separated token addresses/IDs
            counterparties: Comma-separated counterparty addresses/entities
            time_last: Time period (e.g., "24h", "7d")
            time_gte: Filter from timestamp (milliseconds)
            time_lte: Filter to timestamp (milliseconds)
            value_gte: Minimum raw token value
            value_lte: Maximum raw token value
            usd_gte: Minimum USD value
            usd_lte: Maximum USD value
            sort_key: Sort field ("time", "value", "usd")
            sort_dir: Sort direction ("asc", "desc")
            limit: Max results
            offset: Pagination offset

        Returns:
            dict: Transfer data or file path
        """
        try:
            data = await self.client.get_transfers(
                base=base,
                chains=chains,
                flow=flow,
                from_addresses=from_addresses,
                to_addresses=to_addresses,
                tokens=tokens,
                counterparties=counterparties,
                time_last=time_last,
                time_gte=time_gte,
                time_lte=time_lte,
                value_gte=value_gte,
                value_lte=value_lte,
                usd_gte=usd_gte,
                usd_lte=usd_lte,
                sort_key=sort_key,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )

            # Parse transfers
            if isinstance(data, dict) and "transfers" in data:
                transfers_list = data["transfers"] or []
                total_count = data.get("count", len(transfers_list))
            elif isinstance(data, list):
                transfers_list = data or []
                total_count = len(transfers_list)
            else:
                transfers_list = []
                total_count = 0

            # Analysis
            analysis = {}
            if self.enable_analysis and self.stats and transfers_list:
                try:
                    usd_values = []

                    for transfer in transfers_list:
                        if "historicalUSD" in transfer and transfer["historicalUSD"]:
                            usd_values.append(float(transfer["historicalUSD"]))

                    if usd_values:
                        usd_array = np.array(usd_values)
                        usd_stats = self.stats.calculate_price_statistics(usd_array)

                        analysis = {
                            "transfer_summary": {
                                "total_usd_value": sum(usd_values),
                                "usd_distribution": usd_stats,
                                "transfer_count": len(transfers_list),
                            }
                        }

                except Exception as e:
                    logger.warning(f"Failed to calculate transfer analysis: {e}")

            response = await self._build_success_response(
                data=transfers_list,
                storage_data_type="transfers",
                storage_prefix="filtered",
                tool_name="get_transfers",
                count=len(transfers_list),
                total=total_count,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except ArkhamAPIError as e:
            return self._build_error_response(e, tool_name="get_transfers")
        except Exception as e:
            logger.error(f"Unexpected error in get_transfers: {e}")
            return self._build_error_response(e, tool_name="get_transfers")

    async def get_token_balances(
        self,
        address: str,
        chains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get token balances for wallet.

        Args:
            address: Wallet address
            chains: Optional chain filter

        Returns:
            dict: Balance data or file path
        """
        try:
            address = self._validate_address(address)

            data = await self.client.get_token_balances(
                address=address,
                chains=chains,
            )

            # Parse balances
            balances_list = []
            if isinstance(data, dict):
                balances_by_chain = data.get("balances", {})
                for chain_name, chain_balances in balances_by_chain.items():
                    if isinstance(chain_balances, list):
                        for balance in chain_balances:
                            balance_copy = balance.copy()
                            balance_copy["chain"] = chain_name
                            balances_list.append(balance_copy)
            elif isinstance(data, list):
                balances_list = data

            # Analysis
            analysis = {}
            if self.enable_analysis and self.stats and balances_list:
                try:
                    usd_values = []

                    for balance in balances_list:
                        if balance.get("usd") is not None:
                            usd_values.append(float(balance["usd"]))

                    if usd_values:
                        usd_array = np.array(usd_values)
                        total_value = sum(usd_values)
                        largest_holding = max(usd_values)

                        # Calculate Gini coefficient inline (measure of inequality)
                        sorted_values = np.sort(usd_array)
                        n = len(sorted_values)
                        cumsum = np.cumsum(sorted_values)
                        gini = (
                            (2 * np.sum((np.arange(1, n + 1)) * sorted_values))
                            / (n * np.sum(sorted_values))
                            - (n + 1) / n
                            if np.sum(sorted_values) > 0
                            else 0
                        )

                        analysis = {
                            "portfolio_summary": {
                                "total_value_usd": round(total_value, 2),
                                "token_count": len(usd_values),
                                "largest_holding_pct": round(
                                    (largest_holding / total_value * 100), 1
                                )
                                if total_value > 0
                                else 0,
                                "gini_coefficient": round(gini, 3),
                                "concentration_level": "high"
                                if gini > 0.7
                                else "moderate"
                                if gini > 0.4
                                else "low",
                            }
                        }

                except Exception as e:
                    logger.warning(f"Failed to calculate portfolio analysis: {e}")

            response = await self._build_success_response(
                data=balances_list,
                storage_data_type="token_balances",
                storage_prefix=address[:10],
                tool_name="get_token_balances",
                address=address,
                count=len(balances_list),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except ArkhamAPIError as e:
            return self._build_error_response(
                e, tool_name="get_token_balances", address=address
            )
        except Exception as e:
            logger.error(f"Unexpected error in get_token_balances: {e}")
            return self._build_error_response(e, tool_name="get_token_balances")

    async def aclose(self) -> None:
        """Close HTTP client and clean up resources."""
        await self.client.aclose()
        logger.debug("Closed ArkhamToolkit")
