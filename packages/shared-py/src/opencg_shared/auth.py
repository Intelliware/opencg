"""Authentication for openCG's Python services (add-identity-and-opa, design D1, D1a, D3, D6).

- Two modes, from `OPENCG__AUTH__MODE`: `oidc` (identity only from a validated
  access token) and `none` (the configured stub identity).
- Access tokens are JWTs from one issuer, checked against its JWKS (RS256 or
  ES256 only), `iss`, `aud`, `exp` and `nbf` with 60 s of leeway.
- Named API keys (`Authorization: Bearer ock_<key>`) work in both modes, but only
  when `OPENCG__ENVIRONMENT=dev`.
- `startup_checks()` refuses unsafe configuration before a service serves traffic.

Tokens are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import HTTPException, Request

from opencg_shared.metrics import record_auth_failure
from opencg_shared.types import IdentityContext

log = logging.getLogger(__name__)

AuthMode = Literal["oidc", "none"]
AuthMethod = Literal["oidc", "none", "api_key"]
Environment = Literal["dev", "test", "staging", "production"]

MODES = ("oidc", "none")
ENVIRONMENTS = ("dev", "test", "staging", "production")
ALLOWED_ALGORITHMS = ["RS256", "ES256"]
CLOCK_SKEW_SECONDS = 60
JWKS_REFETCH_INTERVAL_SECONDS = 30.0
API_KEY_PREFIX = "ock_"
REMOVED_STOPGAP_VARIABLES = ("OPENCG__ADMIN_UI__PASSWORD", "OPENCG__MCP__OAUTH_PASSWORD")
LOOPBACK_NAMES = {"localhost"}
MIGRATION_DOC = "docs/OPERATIONS.md, section 'Migrating from the shared-password gate'"

FailureCode = Literal[
    "token_missing", "token_expired", "token_invalid", "issuer_unreachable", "api_key_disabled"
]


class ConfigError(RuntimeError):
    """Unsafe or invalid auth configuration; the service must not start."""


class AuthError(Exception):
    """Authentication failed; maps to HTTP 401 with `code`."""

    def __init__(self, code: FailureCode, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ApiKey:
    name: str
    key_sha256: str
    principal: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    environment: Environment
    issuer: str
    internal_url: str
    audience: str
    principal_claim: str
    roles_claim: str
    tenant_claim: str
    bind_address: str
    tenant: str
    stub_principal: str
    stub_roles: tuple[str, ...]
    api_keys_file: str = ""
    legacy_http_token: str = ""
    api_keys: tuple[ApiKey, ...] = field(default_factory=tuple)

    @property
    def discovery_base(self) -> str:
        return (self.internal_url or self.issuer).rstrip("/")


@dataclass(frozen=True)
class AuthenticatedIdentity:
    identity: IdentityContext
    auth_method: AuthMethod
    # The Authorization header value to forward to other openCG services, if any.
    bearer: str | None = None


# --- configuration --------------------------------------------------------------


def _env(env: Mapping[str, str], key: str, default: str = "") -> str:
    return (env.get(key) or default).strip()


def load_api_keys(path: str) -> tuple[ApiKey, ...]:
    """`OPENCG__AUTH__API_KEYS_FILE`: a JSON list of `{name, key_sha256, principal, roles}`."""
    if not path:
        return ()
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"OPENCG__AUTH__API_KEYS_FILE: cannot read {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError("OPENCG__AUTH__API_KEYS_FILE must contain a JSON list")
    keys = []
    for i, entry in enumerate(raw):
        try:
            digest = str(entry["key_sha256"]).lower()
            bytes.fromhex(digest)
            if len(digest) != 64:
                raise ValueError("key_sha256 must be 64 hex characters")
            keys.append(
                ApiKey(
                    name=str(entry["name"]),
                    key_sha256=digest,
                    principal=str(entry["principal"]),
                    roles=tuple(str(r) for r in entry.get("roles", [])),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"OPENCG__AUTH__API_KEYS_FILE: entry {i} is invalid: {exc}") from exc
    return tuple(keys)


def settings_from_env(
    *,
    tenant: str,
    stub_principal: str,
    stub_roles: list[str] | tuple[str, ...],
    env: Mapping[str, str] | None = None,
) -> AuthSettings:
    """Read auth settings. Raises ConfigError for values no service may start with."""
    env = os.environ if env is None else env
    mode = _env(env, "OPENCG__AUTH__MODE", "none").lower()
    if mode not in MODES:
        raise ConfigError(f"OPENCG__AUTH__MODE must be 'oidc' or 'none', got {mode!r}")
    environment = _env(env, "OPENCG__ENVIRONMENT", "production").lower()
    if environment not in ENVIRONMENTS:
        raise ConfigError(
            f"OPENCG__ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}, got {environment!r}"
        )
    keys_file = _env(env, "OPENCG__AUTH__API_KEYS_FILE")
    return AuthSettings(
        mode=mode,  # type: ignore[arg-type]
        environment=environment,  # type: ignore[arg-type]
        issuer=_env(env, "OPENCG__AUTH__OIDC__ISSUER").rstrip("/"),
        internal_url=_env(env, "OPENCG__AUTH__OIDC__INTERNAL_URL").rstrip("/"),
        audience=_env(env, "OPENCG__AUTH__OIDC__AUDIENCE", "opencg"),
        principal_claim=_env(env, "OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM", "preferred_username"),
        roles_claim=_env(env, "OPENCG__AUTH__OIDC__ROLES_CLAIM", "roles"),
        tenant_claim=_env(env, "OPENCG__AUTH__OIDC__TENANT_CLAIM"),
        bind_address=_env(env, "OPENCG__BIND_ADDRESS", "127.0.0.1"),
        tenant=tenant,
        stub_principal=stub_principal,
        stub_roles=tuple(stub_roles),
        api_keys_file=keys_file,
        legacy_http_token=_env(env, "OPENCG__MCP__HTTP_TOKEN"),
        api_keys=load_api_keys(keys_file),
    )


def is_loopback(address: str) -> bool:
    host = address.strip().strip("[]")
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def startup_checks(settings: AuthSettings, env: Mapping[str, str] | None = None) -> None:
    """Raise ConfigError (the service must exit) for unsafe configuration."""
    env = os.environ if env is None else env
    for var in REMOVED_STOPGAP_VARIABLES:
        if _env(env, var):
            raise ConfigError(
                f"{var} is set, but the shared-secret stopgap was removed. "
                f"Configure OIDC instead; see {MIGRATION_DOC}."
            )
    if settings.mode == "none" and not is_loopback(settings.bind_address):
        raise ConfigError(
            "OPENCG__AUTH__MODE=none (no authentication) is only allowed on loopback, "
            f"but OPENCG__BIND_ADDRESS={settings.bind_address!r}. Use OPENCG__AUTH__MODE=oidc."
        )
    if settings.mode == "oidc":
        if not settings.issuer:
            raise ConfigError("OPENCG__AUTH__MODE=oidc requires OPENCG__AUTH__OIDC__ISSUER")
        if not settings.audience:
            raise ConfigError("OPENCG__AUTH__MODE=oidc requires OPENCG__AUTH__OIDC__AUDIENCE")
    if settings.environment != "dev":
        if settings.api_keys or settings.api_keys_file:
            raise ConfigError(
                "OPENCG__AUTH__API_KEYS_FILE is set, but API keys are only allowed when "
                f"OPENCG__ENVIRONMENT=dev (it is {settings.environment!r})"
            )
        if settings.legacy_http_token:
            raise ConfigError(
                "OPENCG__MCP__HTTP_TOKEN is set, but static tokens are only allowed when "
                f"OPENCG__ENVIRONMENT=dev (it is {settings.environment!r})"
            )
    if settings.mode == "none":
        log.warning("auth mode is 'none': requests run as the stub identity, unauthenticated")


def hash_api_key(raw_key: str) -> str:
    """SHA-256 (lowercase hex) of the full key, including its `ock_` prefix."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# --- JWKS ---------------------------------------------------------------------------


def _rewrite_origin(url: str, base: str) -> str:
    """Point `url` at `base`'s scheme and host (Keycloak advertises its public hostname)."""
    u, b = urlparse(url), urlparse(base)
    return u._replace(scheme=b.scheme, netloc=b.netloc).geturl()


class JwksCache:
    """Discovery + JWKS from the internal URL; refetch on unknown `kid`, at most every 30 s."""

    def __init__(self, settings: AuthSettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=5.0)
        self._keys: dict[str, jwt.PyJWK] = {}
        self._jwks_uri: str | None = None
        self._last_fetch = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _discover(self) -> str:
        if self._jwks_uri:
            return self._jwks_uri
        url = f"{self._settings.discovery_base}/.well-known/openid-configuration"
        resp = await self._client.get(url)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]
        if self._settings.internal_url:
            jwks_uri = _rewrite_origin(jwks_uri, self._settings.internal_url)
        self._jwks_uri = jwks_uri
        return jwks_uri

    async def _fetch(self) -> None:
        self._last_fetch = time.monotonic()
        try:
            resp = await self._client.get(await self._discover())
            resp.raise_for_status()
            keys: dict[str, jwt.PyJWK] = {}
            for data in resp.json().get("keys", []):
                if data.get("use", "sig") != "sig" or "kid" not in data:
                    continue
                try:
                    keys[data["kid"]] = jwt.PyJWK(data)
                except jwt.PyJWTError:
                    continue
            self._keys = keys
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise AuthError("issuer_unreachable", f"cannot load issuer keys: {exc}") from exc

    async def key_for(self, kid: str) -> jwt.PyJWK:
        if kid in self._keys:
            return self._keys[kid]
        if not self._keys or time.monotonic() - self._last_fetch >= JWKS_REFETCH_INTERVAL_SECONDS:
            await self._fetch()
        key = self._keys.get(kid)
        if key is None:
            raise AuthError("token_invalid", "unknown signing key")
        return key


# --- claim mapping ---------------------------------------------------------------------


def _claim_path(claims: Mapping[str, Any], path: str) -> Any:
    cur: Any = claims
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def identity_from_claims(claims: Mapping[str, Any], settings: AuthSettings) -> IdentityContext:
    principal = claims.get(settings.principal_claim) or claims.get("sub")
    if not principal:
        raise AuthError("token_invalid", "token has no principal claim and no sub")
    roles_value = _claim_path(claims, settings.roles_claim) if settings.roles_claim else None
    roles = tuple(str(r) for r in roles_value) if isinstance(roles_value, list) else ()
    tenant = settings.tenant
    if settings.tenant_claim:
        tenant = str(_claim_path(claims, settings.tenant_claim) or settings.tenant)
    return IdentityContext(principal=str(principal), roles=roles, tenant=tenant)


# --- authenticator ------------------------------------------------------------------------


class Authenticator:
    def __init__(self, settings: AuthSettings, jwks: JwksCache | None = None) -> None:
        self.settings = settings
        self._jwks = jwks if jwks is not None else JwksCache(settings)

    async def close(self) -> None:
        await self._jwks.close()

    def stub_identity(self) -> IdentityContext:
        s = self.settings
        return IdentityContext(principal=s.stub_principal, roles=s.stub_roles, tenant=s.tenant)

    async def verify_token(self, token: str) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("token_invalid", "malformed token") from exc
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            raise AuthError("token_invalid", f"algorithm {header.get('alg')!r} is not allowed")
        key = await self._jwks.key_for(str(header.get("kid", "")))
        try:
            return jwt.decode(
                token,
                key=key.key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired", "token expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthError("token_invalid", str(exc)) from exc

    def _api_key(self, raw: str) -> AuthenticatedIdentity:
        s = self.settings
        if s.environment != "dev":
            raise AuthError("api_key_disabled", "API keys are only accepted in the dev environment")
        digest = hash_api_key(raw)
        for key in s.api_keys:
            if hmac.compare_digest(digest, key.key_sha256):
                return AuthenticatedIdentity(
                    identity=IdentityContext(
                        principal=key.principal, roles=key.roles, tenant=s.tenant
                    ),
                    auth_method="api_key",
                    bearer=f"Bearer {raw}",
                )
        raise AuthError("token_invalid", "unknown API key")

    def _legacy_token(self, raw: str) -> AuthenticatedIdentity | None:
        s = self.settings
        if s.environment == "dev" and s.legacy_http_token:
            if hmac.compare_digest(raw.encode(), s.legacy_http_token.encode()):
                return AuthenticatedIdentity(
                    identity=self.stub_identity(), auth_method="api_key", bearer=f"Bearer {raw}"
                )
        return None

    async def authenticate(self, authorization: str | None) -> AuthenticatedIdentity:
        raw = ""
        if authorization:
            scheme, _, value = authorization.strip().partition(" ")
            if scheme.lower() == "bearer":
                raw = value.strip()
        if raw.startswith(API_KEY_PREFIX):
            return self._api_key(raw)
        if raw:
            legacy = self._legacy_token(raw)
            if legacy is not None:
                return legacy
        if self.settings.mode == "none":
            return AuthenticatedIdentity(identity=self.stub_identity(), auth_method="none")
        if not raw:
            raise AuthError("token_missing", "no bearer token")
        claims = await self.verify_token(raw)
        return AuthenticatedIdentity(
            identity=identity_from_claims(claims, self.settings),
            auth_method="oidc",
            bearer=f"Bearer {raw}",
        )


# --- FastAPI glue ----------------------------------------------------------------------------

OPEN_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


def unauthorized(error: AuthError, settings: AuthSettings) -> HTTPException:
    headers = {
        "WWW-Authenticate": f'Bearer error="invalid_token", error_description="{error.code}"'
    }
    if error.code == "token_missing":
        headers = {"WWW-Authenticate": "Bearer"}
    return HTTPException(
        status_code=401,
        detail={"code": error.code, "message": "authentication required"},
        headers=headers,
    )


def make_auth_dependency(service: str):
    """FastAPI dependency: authenticate the request and store it on `request.state.auth`.

    Expects `request.app.state.authenticator`. Health and metrics paths never reach it.
    """

    async def dependency(request: Request) -> AuthenticatedIdentity:
        authenticator: Authenticator = request.app.state.authenticator
        try:
            auth = await authenticator.authenticate(request.headers.get("authorization"))
        except AuthError as exc:
            record_auth_failure(service, exc.code)
            log.info("authentication failed on %s: %s", request.url.path, exc.code)
            raise unauthorized(exc, authenticator.settings) from None
        request.state.auth = auth
        return auth

    return dependency
