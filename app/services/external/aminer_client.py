"""AMiner API HTTP client."""
from __future__ import annotations

import httpx

from app.config import settings

OFFICIAL_BASE_URL = "https://datacenter.aminer.cn/gateway/open_platform/api"


class AMinerClient:
    """HTTP client for AMiner API."""

    def __init__(self):
        self.api_key = settings.AMINER_API_KEY
        self.scholar_detail_url = settings.AMINER_SCHOLAR_DETAIL_URL

    def _get_headers(self, require_auth: bool = True) -> dict[str, str]:
        """Build request headers with Authorization token."""
        headers = {
            "Content-Type": "application/json;charset=utf-8",
        }
        if require_auth:
            if not self.api_key:
                raise ValueError("AMINER_API_KEY not configured in .env")
            headers["Authorization"] = self.api_key
        return headers

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
        url = f"{OFFICIAL_BASE_URL}/person/search"
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
        url = f"{OFFICIAL_BASE_URL}/organization/search"
        payload = {"name": name, "size": size}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def _get_scholar_detail_from_official(
        self,
        aminer_id: str,
        force_refresh: bool = False,
    ) -> dict:
        """Fallback path: query official AMiner detail endpoint."""
        url = f"{OFFICIAL_BASE_URL}/person/detail"
        params = {"id": aminer_id, "force_refresh": force_refresh}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers=self._get_headers(require_auth=True),
            )
            response.raise_for_status()
            return response.json()

    async def get_scholar_detail(
        self,
        aminer_id: str,
        force_refresh: bool = False,
    ) -> dict:
        """Get scholar detailed information by scholar ID.

        Args:
            aminer_id: AMiner scholar ID
            force_refresh: Whether to bypass cache in upstream service

        Returns:
            Scholar detail API response dict

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        params = {"id": aminer_id, "force_refresh": force_refresh}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Primary detail source: proxy endpoint, no AMINER_API_KEY required.
                response = await client.get(self.scholar_detail_url, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                # Fallback to official endpoint when key exists.
                if self.api_key:
                    return await self._get_scholar_detail_from_official(
                        aminer_id,
                        force_refresh=force_refresh,
                    )
                raise


# Singleton instance
_client: AMinerClient | None = None


def get_aminer_client() -> AMinerClient:
    """Get or create AMiner client singleton."""
    global _client
    if _client is None:
        _client = AMinerClient()
    return _client
