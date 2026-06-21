"""Pytest fixtures for AMIS E2E integration tests."""

import asyncio
import logging
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio

from e2e.config import TestConfig
from e2e.clients import AMISCoreClient, AMISLabClient, AuthClient

log = logging.getLogger(__name__)


async def get_auth_token_via_login(config: TestConfig) -> str:
    """Authenticate against the Auth Service using configured credentials.

    Falls back to the session-scoped auth_token fixture if login fails.
    """
    try:
        async with AuthClient(config.auth_url, timeout=10.0) as auth:
            resp = await auth.login(config.test_user, config.test_password)
            token = resp.get("access_token")
            if token:
                log.info("Authenticated as '%s' via Auth Service", config.test_user)
                return token
    except Exception as exc:
        log.warning("Auth Service login failed (%s). Ensure user '%s' exists in the auth DB.", exc, config.test_user)
    raise RuntimeError(
        f"Could not log in user '{config.test_user}' against {config.auth_url}. "
        "Either seed the user in the auth service or fall back to the session auth_token fixture."
    )


@pytest.fixture(scope="session")
def research_context_id() -> str:
    """Fixed research context UUID for all AMIS tests in a session."""
    return str(uuid4())


@pytest_asyncio.fixture
async def amis_core_client(
    config: TestConfig, auth_token: str
) -> AsyncGenerator[AMISCoreClient, None]:
    """Provide AMISCoreClient for testing."""
    async with AMISCoreClient(
        base_url=config.amis_core_url,
        token=auth_token,
        timeout=config.timeout_slow,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def amis_lab_client(
    config: TestConfig, auth_token: str
) -> AsyncGenerator[AMISLabClient, None]:
    """Provide AMISLabClient for testing."""
    async with AMISLabClient(
        base_url=config.amis_lab_url,
        token=auth_token,
        timeout=180.0,  # Dataset generation can be slow with MDS fetch
    ) as client:
        yield client


async def poll_validation_job(
    lab_client: AMISLabClient,
    job_id: str,
    timeout: float = 120.0,
    interval: float = 2.0,
) -> dict:
    """Poll Lab validation job until it completes or times out."""
    elapsed = 0.0
    while elapsed < timeout:
        job = await lab_client.get_validation_job(job_id)
        status = job.get("status", "UNKNOWN")
        if status in ("COMPLETED", "FAILED"):
            return job
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Validation job {job_id} did not complete within {timeout}s")
