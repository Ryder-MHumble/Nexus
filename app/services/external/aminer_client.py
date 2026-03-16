"""AMiner API HTTP client."""
from __future__ import annotations

import httpx

from app.config import settings

BASE_URL = "https://datacenter.aminer.cn/gateway/open_platform/api"


class AMinerClient:
    """HTTP client for AMiner API."""

    def __init__(self):
        self.api_key = settings.AMINER_API_KEY
        if not self.api_key:
            raise ValueError("AMINER_API_KEY not configured in .env")

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with Authorization token."""
        return {
            "Content-Type": "application/json;charset=utf-8",
            "Authorization": self.api_key,
        }

    async def search_scholars(
        self,
        name: str,
        org: str,
        size: int = 10,
        offset: int = 0,
    ) -> dict:
        """Search scholars by name and organization.

        Args:
            name: Scholar name
            org: Organization org_name (from institution.json)
            size: Number of results to return
            offset: Pagination offset

        Returns:
            AMiner API response dict

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        url = f"{BASE_URL}/person/search"
        payload = {
            "name": name,
            "org": org,
            "size": size,
            "offset": offset,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def search_organizations(self, name: str, size: int = 3) -> dict:
        """Search organizations by name on AMiner to obtain standardized org_name.

        Args:
            name: Institution name (Chinese preferred)
            size: Max results to return

        Returns:
            AMiner API response dict

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        url = f"{BASE_URL}/org/search"
        params = {"name": name, "size": size}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                params=params,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_scholar_detail(self, aminer_id: str) -> dict:
        """Get scholar detailed information by AMiner ID.

        Args:
            aminer_id: AMiner scholar ID

        Returns:
            AMiner API response dict

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        url = f"{BASE_URL}/person/detail"
        params = {"id": aminer_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()


# Singleton instance
_client: AMinerClient | None = None


def get_aminer_client() -> AMinerClient:
    """Get or create AMiner client singleton."""
    global _client
    if _client is None:
        _client = AMinerClient()
    return _client
