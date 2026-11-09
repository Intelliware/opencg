"""Validate repository URLs submitted over HTTP before they reach `git clone`.

The ingestion HTTP API (and the admin UI "Run now" form that proxies to it)
accepts a URL from the network and hands it to git. Without checks that is a
server-side request forgery and argument-injection surface:

* `--upload-pack=…` / `-c …` would be parsed by git as options;
* `ext::` and `file://` transports run commands or read the container's disk;
* hostnames like `pipeline`, `postgres` or `169.254.169.254` reach services
  that are only meant to be compose-internal.

This guard is applied to HTTP-submitted URLs only. The CLI is operator-driven
and stays unrestricted. DNS is checked at submission time, so a host that
re-resolves (DNS rebinding) between check and clone is not covered; treat this
as a stopgap alongside the admin access gate, not as a network policy.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

ALLOWED_SCHEMES = frozenset({"https", "ssh", "git"})

# scp-like syntax: [user@]host:path (no scheme, no leading slash before host).
_SCP_LIKE = re.compile(r"^(?:(?P<user>[\w.+-]+)@)?(?P<host>[A-Za-z0-9.-]+):(?!//)(?P<path>.+)$")

Resolver = Callable[..., list]


class RepoUrlError(ValueError):
    """Raised when a submitted repository URL is not allowed."""


def validate_repo_url(
    url: str,
    *,
    allowed_hosts: Iterable[str] = (),
    local_roots: Iterable[str] = (),
    resolver: Resolver = socket.getaddrinfo,
) -> str:
    """Return `url` unchanged if it is safe to clone, else raise RepoUrlError."""
    # Most specific checks first, so the error names the actual danger.
    if url.lstrip().startswith("-"):
        raise RepoUrlError("repository URL must not start with '-' (git option injection)")
    transport = re.match(r"^\s*([A-Za-z][\w+.-]*)::", url)
    if transport:
        raise RepoUrlError(f"scheme '{transport.group(1)}::' (git remote helper) is not allowed")
    if url != url.strip() or any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise RepoUrlError("repository URL must not contain whitespace or control characters")

    roots = [Path(r).resolve() for r in local_roots if r]
    allowed = {h.strip().lower() for h in allowed_hosts if h.strip()}

    if url.startswith("/") or url.lower().startswith("file:"):
        path = unquote(urlsplit(url).path) if url.lower().startswith("file:") else url
        _check_local(path, roots)
        return url

    if "://" in url:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise RepoUrlError(
                f"scheme '{scheme}' is not allowed; use one of {sorted(ALLOWED_SCHEMES)}"
            )
        if parts.password:
            raise RepoUrlError("embedded password in repository URL is not allowed")
        host = (parts.hostname or "").lower()
    else:
        match = _SCP_LIKE.match(url)
        if not match:
            raise RepoUrlError(
                f"unsupported scheme or form; use one of {sorted(ALLOWED_SCHEMES)} "
                "or user@host:path"
            )
        host = match.group("host").lower()

    if not host:
        raise RepoUrlError("repository URL has no host")
    if host in allowed:
        return url
    _check_public(host, resolver)
    return url


def _check_local(path: str, roots: list[Path]) -> None:
    if not roots:
        raise RepoUrlError(
            "local repository paths are disabled; set OPENCG__INGESTION__GIT__LOCAL_ROOTS"
        )
    target = Path(path).resolve()
    if not any(target == root or root in target.parents for root in roots):
        raise RepoUrlError("local repository path is outside the allowed local roots")


def _check_public(host: str, resolver: Resolver) -> None:
    try:
        infos = resolver(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise RepoUrlError(f"cannot resolve repository host '{host}'") from exc
    if not infos:
        raise RepoUrlError(f"cannot resolve repository host '{host}'")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not address.is_global:
            raise RepoUrlError(
                f"repository host '{host}' resolves to a non-public address ({address}); "
                "allow-list it with OPENCG__INGESTION__GIT__ALLOWED_HOSTS if intended"
            )
