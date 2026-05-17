"""
Async REST client for Authentication Service.

Handles user registration, login, token refresh, and password management.
"""

from typing import Optional
import httpx


class AuthClient:
    """
    Async REST client for Authentication Service.

    Manages user credentials, JWT tokens, and RBAC operations.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def register(
        self,
        email: str,
        password: str,
        full_name: str = "Test User",
    ) -> dict:
        """
        Register a new user.

        Args:
            email: User email address
            password: User password
            full_name: Full name of user

        Returns:
            User registration response
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
            }
        )
        response.raise_for_status()
        return response.json()

    async def login(
        self,
        username: str,
        password: str,
    ) -> dict:
        """
        Login user and get access token.

        Args:
            username: User username (email address)
            password: User password

        Returns:
            Login response with access_token. Refresh token is in httpOnly cookie.
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.post(
            "/auth/login",
            json={
                "username": username,
                "password": password,
            }
        )
        response.raise_for_status()
        data = response.json()

        # Store cookies (including refresh_token) for subsequent requests
        # httpx client automatically handles cookies
        return data

    async def refresh_token(self) -> dict:
        """
        Refresh access token using httpOnly refresh token cookie.

        Returns:
            New access token response
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.post("/auth/refresh")
        response.raise_for_status()
        return response.json()

    async def validate_token(self, token: str) -> dict:
        """
        Validate JWT token by sending authenticated request.

        Args:
            token: JWT access token

        Returns:
            Response with user info if token is valid

        Raises:
            httpx.HTTPError: If token is invalid or expired
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        # Use the token to make an authenticated request to a protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.get(
            "/auth/me",
            headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def get_user_roles(self, token: str) -> list:
        """
        Get user roles from token-authenticated endpoint.

        Args:
            token: JWT access token

        Returns:
            List of user roles from user object
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.get(
            "/auth/me",
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        # Auth service returns roles within the user object
        return data.get("roles", [])

    async def change_password(
        self,
        token: str,
        old_password: str,
        new_password: str,
    ) -> dict:
        """
        Change user password (if implemented).

        Args:
            token: JWT access token
            old_password: Current password
            new_password: New password

        Returns:
            Response indicating success
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.post(
            "/auth/change-password",
            headers=headers,
            json={
                "old_password": old_password,
                "new_password": new_password,
            }
        )
        response.raise_for_status()
        return response.json()

    async def logout(self, token: str) -> dict:
        """
        Logout user.

        Args:
            token: JWT access token

        Returns:
            Response indicating logout success (usually 204 No Content)
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.post(
            "/auth/logout",
            headers=headers,
        )
        response.raise_for_status()
        return response.json() if response.text else {}
