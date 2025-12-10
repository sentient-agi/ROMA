"""PTC Service Client for ROMA integration."""

import httpx
from typing import Optional, List, Dict, Any
from loguru import logger


class PTCClient:
    """Client for communicating with PTC (Prompt-Test-Code) service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8002",
        timeout: float = 300.0,
    ):
        """
        Initialize PTC client.

        Args:
            base_url: PTC service URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def health_check(self) -> Dict[str, Any]:
        """Check if PTC service is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"PTC health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def generate_code(
        self,
        task_description: str,
        requirements: Optional[List[str]] = None,
        language: str = "python",
    ) -> Dict[str, Any]:
        """
        Generate code using PTC service.

        Args:
            task_description: What the code should do
            requirements: List of specific requirements
            language: Programming language (default: python)

        Returns:
            Dict with:
                - code: Generated code
                - language: Programming language
                - provider: LLM provider used (e.g., kimi)
                - tokens_used: Total tokens consumed
                - cost_usd: Cost in USD
        """
        try:
            payload = {
                "task_description": task_description,
                "requirements": requirements or [],
                "language": language,
            }

            logger.info(f"Requesting code generation from PTC: {task_description[:100]}...")

            response = await self.client.post(
                f"{self.base_url}/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"PTC generated {len(result.get('code', ''))} chars using "
                f"{result.get('provider', 'unknown')} "
                f"(cost: ${result.get('cost_usd', 0):.6f})"
            )

            return result

        except httpx.HTTPError as e:
            logger.error(f"PTC request failed: {e}")
            raise RuntimeError(f"Failed to generate code via PTC: {e}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global PTC client instance (lazy initialized)
_ptc_client: Optional[PTCClient] = None


def get_ptc_client(
    base_url: str = "http://localhost:8002",
    timeout: float = 300.0,
) -> PTCClient:
    """Get or create global PTC client instance."""
    global _ptc_client
    if _ptc_client is None:
        _ptc_client = PTCClient(base_url=base_url, timeout=timeout)
    return _ptc_client
