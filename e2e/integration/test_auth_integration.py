"""
Integration test — Authentication Service login / token / RBAC contract.

Pair under test: any client ↔ authentication-service (and a representative
downstream service for cross-service RBAC).

Contract:
    1. POST /auth/login with a known seeded user returns HTTP 200 with an
       access_token in the body and a refresh_token in an httpOnly cookie.
    2. The access_token decodes to a JWT carrying the canonical
       smarttrade-common claim set (sub/iat/exp/type=access/iss/aud) so
       downstream services can validate it without an auth-service round-trip.
    3. Login with a wrong-but-shape-valid password returns 401 AUTH_004.
    4. GET /auth/me with no token returns 401 AUTH_004 ("Missing or invalid
       token").
    5. GET /auth/me with a syntactically invalid Bearer token returns 401
       AUTH_001 (decode failure).
    6. GET /auth/me with a structurally-valid but expired JWT returns 401.
    7. POST /auth/refresh using the httpOnly refresh cookie set at login
       returns a new access_token; the new token decodes and matches the
       same user identity.
    8. A downstream service (broker-adapter-service) enforces the same
       Bearer-token contract: a valid token reaches the route handler; an
       invalid or missing token is rejected with 401 before the handler
       runs.

This test is the canonical guard for the JWT contract that every other
service in the stack assumes. If any of these break, every protected
endpoint in the platform breaks together.

Past regressions guarded:
    - UserOut.email was Optional[EmailStr] (strict), but the seeded admin
      uses `admin@smarttrade.local` (RFC 6761 reserved TLD). /auth/me
      then 500'd for any account with a dev/test-shaped email. The DTO is
      now Optional[str] on the read side; RegisterRequest still validates
      strictly on insert.
    - SchemaRegistry not being populated from EventCatalog at startup
      previously broke order publishing — auth itself was fine, but the
      JWT validation path runs first on every protected endpoint, so this
      test acts as a quick smoke against that whole layer.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from jose import jwt as jose_jwt

from e2e.clients import AuthClient


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def auth_client(config):
    """Provide an AuthClient bound to the configured auth-service base URL.

    Function-scoped so each test gets a fresh cookie jar — tests for the
    refresh path rely on a clean session that only carries the cookie set
    by the login under test.
    """
    async with AuthClient(base_url=config.auth_url, timeout=config.timeout_medium) as client:
        yield client


def _decode_unverified(token: str) -> dict:
    """Decode a JWT without verifying the signature.

    The shared HS256 secret is not always exported to the test process
    (CI may inject it only into service containers). Claims-level
    assertions are sufficient because the publisher's signature is
    re-validated by every downstream service anyway.
    """
    return jose_jwt.get_unverified_claims(token)


# ──────────────────────────────────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────────────────────────────────


async def test_login_with_seeded_admin_returns_valid_access_token(
    auth_client: AuthClient,
    config,
):
    """Login with the seeded admin (authentication_service.seeder.seed_admin)
    succeeds and returns an access_token that decodes to the expected
    smarttrade-common claim set.
    """
    response = await auth_client.login(
        username=config.test_user,
        password=config.test_password,
    )

    assert "access_token" in response, (
        f"Login response missing access_token. Body: {response}"
    )
    assert response["access_token"], "access_token field is empty"

    claims = _decode_unverified(response["access_token"])
    assert "sub" in claims, f"Token missing 'sub' claim: {claims}"
    assert "exp" in claims, f"Token missing 'exp' claim: {claims}"
    assert "iat" in claims, f"Token missing 'iat' claim: {claims}"
    assert claims.get("type") == "access", (
        f"Token type should be 'access' for an access token; got "
        f"{claims.get('type')!r}. Downstream services that gate on type=='access' "
        f"would reject this token."
    )
    assert claims.get("iss") == "auth-service", (
        f"Token issuer should be 'auth-service'; got {claims.get('iss')!r}. "
        f"smarttrade-common's JWT validator pins this value."
    )
    assert claims.get("aud") == "smarttrade-services", (
        f"Token audience should be 'smarttrade-services'; got {claims.get('aud')!r}."
    )


async def test_login_sets_refresh_token_as_httponly_cookie(
    auth_client: AuthClient,
    config,
):
    """Login MUST set the refresh_token as an httpOnly cookie, NOT return
    it in the response body. The frontend relies on this to defend
    against XSS exfiltration of the long-lived refresh token.
    """
    response = await auth_client.login(
        username=config.test_user,
        password=config.test_password,
    )

    # refresh_token must not leak into the JSON body.
    assert "refresh_token" not in response or not response.get("refresh_token"), (
        f"Login response leaked refresh_token in body: {response}. "
        f"Refresh token must only be set as an httpOnly cookie."
    )

    # The cookie must be present in the client's cookie jar after login.
    cookies = auth_client._client.cookies
    assert cookies.get("refresh_token"), (
        "refresh_token cookie was not set by /auth/login. The frontend "
        "session-persistence path depends on this cookie being present."
    )


# ──────────────────────────────────────────────────────────────────────────
# Authentication failure modes
# ──────────────────────────────────────────────────────────────────────────


async def test_login_with_wrong_password_returns_401(
    auth_client: AuthClient,
    config,
):
    """Wrong password → 401 AUTH_004 'Invalid Credentials'.

    A common silent regression is the seeder rebuilding the admin's
    password hash on every startup with a different algorithm — old
    hashes verify but new ones don't, and login starts failing for
    accounts that previously worked. This test catches that class of
    bug.
    """
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await auth_client.login(
            username=config.test_user,
            password="DefinitelyWrong!" + uuid.uuid4().hex[:8],
        )
    assert exc_info.value.response.status_code == 401, (
        f"Expected 401 for wrong password; got "
        f"{exc_info.value.response.status_code}. Body: "
        f"{exc_info.value.response.text}"
    )


async def test_me_without_authorization_header_returns_401(
    config,
):
    """GET /auth/me without an Authorization header is rejected at the
    middleware layer with 401 AUTH_004 'Missing or invalid token'.

    The same RBAC middleware sits in front of every protected endpoint
    across every service, so this is the single gate that protects the
    platform from anonymous calls.
    """
    async with httpx.AsyncClient(
        base_url=config.auth_url, timeout=config.timeout_medium
    ) as client:
        response = await client.get("/auth/me")
    assert response.status_code == 401, (
        f"Expected 401 for /auth/me without a token; got "
        f"{response.status_code}. Body: {response.text}"
    )


async def test_me_with_malformed_token_returns_401(
    auth_client: AuthClient,
):
    """A syntactically invalid Bearer token is rejected with 401 AUTH_001
    'Invalid header / decode failure'.

    The decode-failure path differs from the 'missing token' path
    (AUTH_004): one means the client sent nothing, the other means the
    client sent garbage. Frontends differentiate so they can route
    'session expired' UI vs 'no session at all'.
    """
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await auth_client.validate_token("not.a.real.jwt")
    assert exc_info.value.response.status_code == 401, (
        f"Expected 401 for malformed token; got "
        f"{exc_info.value.response.status_code}. Body: "
        f"{exc_info.value.response.text}"
    )


async def test_me_with_expired_token_returns_401(
    config,
):
    """An access token whose `exp` is in the past is rejected even if it
    is otherwise correctly signed.

    Requires JWT_SECRET_KEY in the test environment so we can mint a
    token matching the running service's verifier. If the secret isn't
    available the test is skipped — we never substitute a different
    secret because that would test 'wrong signature', not 'expired'.
    """
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        pytest.skip(
            "JWT_SECRET_KEY not exported into the test environment; cannot "
            "mint a structurally-valid expired token. Set JWT_SECRET_KEY to "
            "match docker-compose.e2e.yml to enable this test."
        )

    now = datetime.utcnow()
    payload = {
        "sub": str(uuid.uuid4()),
        "roles": ["admin"],
        "type": "access",
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(seconds=30)).timestamp()),  # expired 30s ago
        "iss": "auth-service",
        "aud": "smarttrade-services",
    }
    expired_token = jose_jwt.encode(payload, secret, algorithm="HS256")

    async with AuthClient(
        base_url=config.auth_url, timeout=config.timeout_medium
    ) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.validate_token(expired_token)
        assert exc_info.value.response.status_code == 401, (
            f"Expected 401 for expired token; got "
            f"{exc_info.value.response.status_code}. Body: "
            f"{exc_info.value.response.text}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Authenticated endpoints & refresh
# ──────────────────────────────────────────────────────────────────────────


async def test_me_returns_user_for_valid_token(
    auth_client: AuthClient,
    config,
):
    """A valid access_token unlocks GET /auth/me and the response reflects
    the same identity (`sub` claim) that the JWT carries.
    """
    login = await auth_client.login(
        username=config.test_user,
        password=config.test_password,
    )
    access_token = login["access_token"]
    claims = _decode_unverified(access_token)

    me = await auth_client.validate_token(access_token)
    assert me.get("id") == claims["sub"], (
        f"/auth/me returned id={me.get('id')!r} but the token's sub was "
        f"{claims['sub']!r}. The user identity must round-trip cleanly."
    )
    assert me.get("username") == config.test_user, (
        f"/auth/me returned username={me.get('username')!r}; expected "
        f"{config.test_user!r}."
    )
    assert "roles" in me and isinstance(me["roles"], list), (
        f"/auth/me must return a roles list; got {me!r}. RBAC enforcement "
        f"downstream reads this list."
    )


async def test_refresh_returns_new_access_token_from_cookie(
    auth_client: AuthClient,
    config,
):
    """The refresh_token cookie set by /auth/login can be exchanged for a
    fresh access_token via /auth/refresh, and the new token represents
    the same identity. The cookie itself is rotated on each refresh.
    """
    login = await auth_client.login(
        username=config.test_user,
        password=config.test_password,
    )
    original_access = login["access_token"]
    original_refresh_cookie = auth_client._client.cookies.get("refresh_token")
    assert original_refresh_cookie, (
        "Cannot run refresh test: /auth/login did not set a refresh_token "
        "cookie."
    )

    refreshed = await auth_client.refresh_token()
    assert "access_token" in refreshed, (
        f"Refresh response missing access_token: {refreshed}"
    )
    new_access = refreshed["access_token"]

    original_claims = _decode_unverified(original_access)
    new_claims = _decode_unverified(new_access)
    assert new_claims["sub"] == original_claims["sub"], (
        f"Refreshed token represents a different user. Old sub="
        f"{original_claims['sub']!r}, new sub={new_claims['sub']!r}."
    )
    assert new_claims.get("type") == "access", (
        "Refreshed token must be an access token (not another refresh)."
    )

    # The new access_token unlocks /auth/me end-to-end (closes the loop:
    # refresh produces something the downstream gate accepts).
    me = await auth_client.validate_token(new_access)
    assert me.get("id") == new_claims["sub"]


async def test_refresh_without_cookie_returns_401(
    config,
):
    """/auth/refresh requires the httpOnly cookie; an unauthenticated
    client (no cookie jar entry, no body field) is rejected.

    Past regression: a previous version of /auth/refresh accepted the
    refresh token in the JSON body. That endpoint was exploitable
    because any leaked refresh token from a client log could be used
    directly. The cookie-only contract is what closes that hole — this
    test pins it.
    """
    async with httpx.AsyncClient(
        base_url=config.auth_url, timeout=config.timeout_medium
    ) as client:
        # No cookie, no body — pure unauthenticated request.
        response = await client.post("/auth/refresh")
    assert response.status_code in (401, 403), (
        f"Expected 401/403 for /auth/refresh without a cookie; got "
        f"{response.status_code}. Body: {response.text}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Cross-service: same JWT contract applies to broker-adapter-service
# ──────────────────────────────────────────────────────────────────────────


async def test_jwt_from_auth_service_is_accepted_by_broker_adapter(
    auth_client: AuthClient,
    config,
    test_account_id,
):
    """A token minted by /auth/login is accepted by broker-adapter-service.

    This validates the contract between services — both sides agree on
    iss/aud/secret. If smarttrade-common's JWT validator drifts away
    from the auth-service token issuer (different aud, different secret,
    different algorithm), every protected endpoint in BAS/PBS/MDS
    starts returning 401 even though /auth/login still works.

    A 401 here means inter-service trust is broken; any non-401 (200,
    404, 422 — whatever the route returns when authenticated) is fine
    because we are only asserting that the request got past the auth
    middleware.
    """
    login = await auth_client.login(
        username=config.test_user,
        password=config.test_password,
    )
    access_token = login["access_token"]

    async with httpx.AsyncClient(
        base_url=config.bas_url, timeout=config.timeout_medium
    ) as client:
        response = await client.get(
            f"/api/v1/orders/{config.broker_id}/{test_account_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert response.status_code != 401, (
        f"broker-adapter-service rejected a token minted by auth-service "
        f"with HTTP 401: {response.text!r}. The two services' JWT "
        f"contracts have drifted — likely different iss/aud or a stale "
        f"shared secret."
    )


async def test_broker_adapter_rejects_invalid_bearer_with_401(
    config,
    test_account_id,
):
    """The same RBAC middleware on broker-adapter-service rejects a
    malformed Bearer header with 401 — the same way auth-service does
    on /auth/me. This proves the gate is wired identically everywhere.
    """
    async with httpx.AsyncClient(
        base_url=config.bas_url, timeout=config.timeout_medium
    ) as client:
        response = await client.get(
            f"/api/v1/orders/{config.broker_id}/{test_account_id}",
            headers={"Authorization": "Bearer not.a.real.jwt"},
        )
    assert response.status_code == 401, (
        f"Expected 401 from broker-adapter-service for malformed token; "
        f"got {response.status_code}. Body: {response.text}"
    )


async def test_broker_adapter_rejects_missing_bearer_with_401(
    config,
    test_account_id,
):
    """No Authorization header at all → 401 from broker-adapter-service.

    Symmetric to the malformed-token case above; one final pin so that
    a future refactor that accidentally makes auth optional on any
    protected route fails this test.
    """
    async with httpx.AsyncClient(
        base_url=config.bas_url, timeout=config.timeout_medium
    ) as client:
        response = await client.get(
            f"/api/v1/orders/{config.broker_id}/{test_account_id}"
        )
    assert response.status_code == 401, (
        f"Expected 401 from broker-adapter-service for missing token; "
        f"got {response.status_code}. Body: {response.text}"
    )
