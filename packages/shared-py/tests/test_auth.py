"""opencg_shared.auth: token validation, claim mapping, API keys, startup checks."""

from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from opencg_shared import auth
from opencg_shared.auth import (
    Authenticator,
    AuthError,
    ConfigError,
    hash_api_key,
    settings_from_env,
    startup_checks,
)

pytestmark = pytest.mark.asyncio

ISSUER = "http://localhost:8380/realms/opencg"
INTERNAL = "http://keycloak:8080/realms/opencg"
JWKS_URL = f"{INTERNAL}/protocol/openid-connect/certs"


def _key(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private, jwk


KEY1, JWK1 = _key("k1")
KEY2, JWK2 = _key("k2")


def _settings(**env):
    base = {
        "OPENCG__AUTH__MODE": "oidc",
        "OPENCG__ENVIRONMENT": "production",
        "OPENCG__AUTH__OIDC__ISSUER": ISSUER,
        "OPENCG__AUTH__OIDC__INTERNAL_URL": INTERNAL,
    }
    base.update(env)
    return settings_from_env(
        tenant="default", stub_principal="local-dev", stub_roles=["admin", "reader"], env=base
    )


def _token(claims=None, *, key=KEY1, kid="k1", alg="RS256", **overrides):
    now = int(time.time())
    body = {
        "iss": ISSUER,
        "aud": ["opencg", "account"],
        "sub": "8f2c-uuid",
        "preferred_username": "alice",
        "roles": ["admin", "reader"],
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    body.update(claims or {})
    for k, v in overrides.items():
        if v is None:
            body.pop(k, None)
        else:
            body[k] = v
    return jwt.encode(body, key, algorithm=alg, headers={"kid": kid})


def _mock_issuer(router, keys):
    router.get(f"{INTERNAL}/.well-known/openid-configuration").mock(
        # Keycloak advertises the public hostname; the verifier must rewrite it.
        return_value=httpx.Response(
            200, json={"issuer": ISSUER, "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"}
        )
    )
    return router.get(JWKS_URL).mock(return_value=httpx.Response(200, json={"keys": keys}))


@pytest.fixture
def issuer():
    with respx.mock(assert_all_called=False) as router:
        yield router


async def _auth(settings, header):
    a = Authenticator(settings)
    try:
        return await a.authenticate(header)
    finally:
        await a.close()


# --- validation ------------------------------------------------------------------------


async def test_valid_token_maps_identity(issuer):
    _mock_issuer(issuer, [JWK1])
    result = await _auth(_settings(), f"Bearer {_token()}")
    assert result.auth_method == "oidc"
    assert result.identity.principal == "alice"
    assert result.identity.roles == ("admin", "reader")
    assert result.identity.tenant == "default"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"exp": int(time.time()) - 120}, "token_expired"),
        ({"nbf": int(time.time()) + 600}, "token_invalid"),
        ({"iss": "http://evil/realms/opencg"}, "token_invalid"),
        ({"aud": "someone-else"}, "token_invalid"),
    ],
)
async def test_rejections(issuer, overrides, code):
    _mock_issuer(issuer, [JWK1])
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), f"Bearer {_token(**overrides)}")
    assert err.value.code == code


async def test_expiry_within_skew_is_accepted(issuer):
    _mock_issuer(issuer, [JWK1])
    result = await _auth(_settings(), f"Bearer {_token(exp=int(time.time()) - 30)}")
    assert result.identity.principal == "alice"


async def test_alg_none_rejected(issuer):
    _mock_issuer(issuer, [JWK1])
    unsigned = jwt.encode({"iss": ISSUER, "aud": "opencg", "sub": "x"}, None, algorithm="none")
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), f"Bearer {unsigned}")
    assert err.value.code == "token_invalid"


async def test_hmac_rejected(issuer):
    _mock_issuer(issuer, [JWK1])
    hs = jwt.encode(
        {"iss": ISSUER, "aud": "opencg", "sub": "x", "exp": int(time.time()) + 60},
        "a-shared-secret-that-is-long-enough-for-hs256",
        algorithm="HS256",
        headers={"kid": "k1"},
    )
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), f"Bearer {hs}")
    assert err.value.code == "token_invalid"


async def test_missing_token(issuer):
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), None)
    assert err.value.code == "token_missing"


async def test_issuer_unreachable(issuer):
    issuer.get(f"{INTERNAL}/.well-known/openid-configuration").mock(
        side_effect=httpx.ConnectError("down")
    )
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), f"Bearer {_token()}")
    assert err.value.code == "issuer_unreachable"


async def test_key_rotation_refetches_once(issuer, monkeypatch):
    route = _mock_issuer(issuer, [JWK1])
    a = Authenticator(_settings())
    try:
        await a.authenticate(f"Bearer {_token()}")
        assert route.call_count == 1
        # Rotation: the IdP now signs with k2. The first fetch was "long ago".
        route.mock(return_value=httpx.Response(200, json={"keys": [JWK1, JWK2]}))
        monkeypatch.setattr(auth, "JWKS_REFETCH_INTERVAL_SECONDS", 0.0)
        result = await a.authenticate(f"Bearer {_token(key=KEY2, kid='k2')}")
        assert result.identity.principal == "alice"
        assert route.call_count == 2
        # A cached kid needs no refetch.
        await a.authenticate(f"Bearer {_token(key=KEY2, kid='k2')}")
        assert route.call_count == 2
    finally:
        await a.close()


async def test_unknown_kid_refetch_is_rate_limited(issuer):
    route = _mock_issuer(issuer, [JWK1])
    a = Authenticator(_settings())
    try:
        await a.authenticate(f"Bearer {_token()}")
        for _ in range(3):
            with pytest.raises(AuthError):
                await a.authenticate(f"Bearer {_token(key=KEY2, kid='k2')}")
        assert route.call_count == 1  # within 30 s: no refetch storm
    finally:
        await a.close()


# --- claim mapping ---------------------------------------------------------------------------


async def test_sub_fallback_and_missing_roles(issuer):
    _mock_issuer(issuer, [JWK1])
    result = await _auth(_settings(), f"Bearer {_token(preferred_username=None, roles=None)}")
    assert result.identity.principal == "8f2c-uuid"
    assert result.identity.roles == ()


async def test_nested_roles_claim(issuer):
    _mock_issuer(issuer, [JWK1])
    token = _token({"realm_access": {"roles": ["reader", "legal"]}}, roles=None)
    settings = _settings(OPENCG__AUTH__OIDC__ROLES_CLAIM="realm_access.roles")
    result = await _auth(settings, f"Bearer {token}")
    assert result.identity.roles == ("reader", "legal")


async def test_tenant_claim(issuer):
    _mock_issuer(issuer, [JWK1])
    settings = _settings(OPENCG__AUTH__OIDC__TENANT_CLAIM="org")
    result = await _auth(settings, f"Bearer {_token({'org': 'acme'})}")
    assert result.identity.tenant == "acme"


# --- none mode and API keys ------------------------------------------------------------------


async def test_none_mode_uses_stub():
    result = await _auth(_settings(OPENCG__AUTH__MODE="none"), None)
    assert result.auth_method == "none"
    assert result.identity.principal == "local-dev"


def _keys_file(tmp_path, raw="ock_test-key-123"):
    f = tmp_path / "keys.json"
    f.write_text(
        json.dumps(
            [
                {
                    "name": "ci",
                    "key_sha256": hash_api_key(raw),
                    "principal": "svc-ci",
                    "roles": ["reader"],
                }
            ]
        )
    )
    return str(f), raw


async def test_api_key_accepted_in_dev_in_oidc_mode(tmp_path):
    path, raw = _keys_file(tmp_path)
    s = _settings(OPENCG__ENVIRONMENT="dev", OPENCG__AUTH__API_KEYS_FILE=path)
    result = await _auth(s, f"Bearer {raw}")
    assert result.auth_method == "api_key"
    assert result.identity.principal == "svc-ci"
    assert result.identity.roles == ("reader",)
    assert result.bearer == f"Bearer {raw}"


async def test_unknown_api_key_rejected(tmp_path):
    path, _ = _keys_file(tmp_path)
    s = _settings(OPENCG__ENVIRONMENT="dev", OPENCG__AUTH__API_KEYS_FILE=path)
    with pytest.raises(AuthError) as err:
        await _auth(s, "Bearer ock_wrong")
    assert err.value.code == "token_invalid"


async def test_api_key_disabled_outside_dev():
    with pytest.raises(AuthError) as err:
        await _auth(_settings(), "Bearer ock_anything")
    assert err.value.code == "api_key_disabled"


async def test_legacy_http_token_in_dev():
    s = _settings(OPENCG__ENVIRONMENT="dev", OPENCG__MCP__HTTP_TOKEN="legacy-token")
    result = await _auth(s, "Bearer legacy-token")
    assert result.auth_method == "api_key"
    assert result.identity.principal == "local-dev"


# --- startup checks ---------------------------------------------------------------------------


def test_unset_environment_is_production():
    s = settings_from_env(tenant="t", stub_principal="p", stub_roles=[], env={})
    assert s.environment == "production"
    assert s.mode == "none"


@pytest.mark.parametrize(
    ("env", "names"),
    [
        ({"OPENCG__AUTH__MODE": "basic"}, "OPENCG__AUTH__MODE"),
        ({"OPENCG__ENVIRONMENT": "qa"}, "OPENCG__ENVIRONMENT"),
    ],
)
def test_invalid_values_refused(env, names):
    with pytest.raises(ConfigError, match=names):
        settings_from_env(tenant="t", stub_principal="p", stub_roles=[], env=env)


def _check(env):
    s = settings_from_env(tenant="t", stub_principal="p", stub_roles=[], env=env)
    startup_checks(s, env)


def test_none_mode_on_network_address_refused():
    with pytest.raises(ConfigError, match="OPENCG__BIND_ADDRESS"):
        _check({"OPENCG__AUTH__MODE": "none", "OPENCG__BIND_ADDRESS": "0.0.0.0"})


@pytest.mark.parametrize("addr", ["127.0.0.1", "::1", "localhost", "[::1]"])
def test_none_mode_on_loopback_ok(addr):
    _check({"OPENCG__AUTH__MODE": "none", "OPENCG__BIND_ADDRESS": addr})


def test_oidc_without_issuer_refused():
    with pytest.raises(ConfigError, match="OPENCG__AUTH__OIDC__ISSUER"):
        _check({"OPENCG__AUTH__MODE": "oidc", "OPENCG__BIND_ADDRESS": "0.0.0.0"})


@pytest.mark.parametrize("var", ["OPENCG__ADMIN_UI__PASSWORD", "OPENCG__MCP__OAUTH_PASSWORD"])
def test_removed_stopgaps_refused(var):
    with pytest.raises(ConfigError, match="docs/OPERATIONS.md"):
        _check({var: "secret"})


def test_api_keys_refused_outside_dev(tmp_path):
    path, _ = _keys_file(tmp_path)
    with pytest.raises(ConfigError, match="OPENCG__AUTH__API_KEYS_FILE"):
        _check({"OPENCG__ENVIRONMENT": "staging", "OPENCG__AUTH__API_KEYS_FILE": path})


def test_http_token_refused_outside_dev():
    with pytest.raises(ConfigError, match="OPENCG__MCP__HTTP_TOKEN"):
        _check({"OPENCG__MCP__HTTP_TOKEN": "x"})


def test_dev_allows_keys(tmp_path):
    path, _ = _keys_file(tmp_path)
    _check({"OPENCG__ENVIRONMENT": "dev", "OPENCG__AUTH__API_KEYS_FILE": path})
