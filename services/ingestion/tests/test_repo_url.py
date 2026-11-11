"""Validation of repository URLs submitted over HTTP (SSRF / injection guard)."""

from __future__ import annotations

import socket

import pytest
from opencg_ingestion.repo_url import RepoUrlError, validate_repo_url
from opencg_shared import openCGConfig

PUBLIC = "140.82.112.3"  # a public address (github.com range)


def resolver_for(mapping: dict[str, list[str]]):
    def _resolve(host: str, *_args, **_kwargs):
        if host not in mapping:
            raise socket.gaierror(f"unknown host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in mapping[host]]

    return _resolve


PUBLIC_RESOLVER = resolver_for({"github.com": [PUBLIC], "gitlab.example.org": [PUBLIC]})


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/anthropics/anthropic-cookbook",
        "https://github.com/anthropics/anthropic-cookbook.git",
        "ssh://git@github.com/org/repo.git",
        "git://github.com/org/repo.git",
        "git@github.com:org/repo.git",
        "https://token-user@gitlab.example.org/group/repo.git",
    ],
)
def test_public_remote_urls_are_accepted(url):
    assert validate_repo_url(url, resolver=PUBLIC_RESOLVER) == url


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("--upload-pack=touch /tmp/pwned", "option"),
        ("-c core.sshCommand=evil", "option"),
        ("ext::sh -c touch% /tmp/pwned", "scheme"),
        ("http://github.com/org/repo.git", "scheme"),
        ("ftp://github.com/org/repo.git", "scheme"),
        ("file:///etc", "local"),
        ("/etc", "local"),
        ("https://user:hunter2@github.com/org/repo.git", "password"),
        ("https://github.com/org/repo .git", "whitespace"),
        ("https:///no-host", "host"),
    ],
)
def test_dangerous_urls_are_rejected(url, reason):
    with pytest.raises(RepoUrlError) as exc:
        validate_repo_url(url, resolver=PUBLIC_RESOLVER)
    assert reason in str(exc.value)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "172.18.0.4", "192.168.1.10", "169.254.169.254", "::1", "fd00::1"],
)
def test_hosts_resolving_to_internal_addresses_are_rejected(address):
    resolver = resolver_for({"pipeline": [address]})
    with pytest.raises(RepoUrlError) as exc:
        validate_repo_url("https://pipeline/repo.git", resolver=resolver)
    assert "non-public" in str(exc.value)


def test_any_internal_address_in_the_answer_is_rejected():
    resolver = resolver_for({"mixed.example.org": [PUBLIC, "10.0.0.1"]})
    with pytest.raises(RepoUrlError):
        validate_repo_url("https://mixed.example.org/r.git", resolver=resolver)


def test_unresolvable_host_is_rejected():
    with pytest.raises(RepoUrlError) as exc:
        validate_repo_url("https://nope.invalid/r.git", resolver=resolver_for({}))
    assert "resolve" in str(exc.value)


def test_allow_listed_internal_host_is_accepted():
    resolver = resolver_for({"git.internal": ["10.1.2.3"]})
    url = "https://git.internal/team/repo.git"
    assert validate_repo_url(url, allowed_hosts=["GIT.internal"], resolver=resolver) == url


def test_local_path_under_allowed_root_is_accepted(tmp_path):
    repo = tmp_path / "opencg-smoke-1"
    repo.mkdir()
    assert validate_repo_url(str(repo), local_roots=[str(tmp_path)]) == str(repo)


def test_local_path_escaping_root_is_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(RepoUrlError) as exc:
        validate_repo_url(str(root / ".." / "elsewhere"), local_roots=[str(root)])
    assert "local" in str(exc.value)


def test_file_url_under_allowed_root_is_accepted(tmp_path):
    url = f"file://{tmp_path}/repo"
    assert validate_repo_url(url, local_roots=[str(tmp_path)]) == url


def test_config_accepts_single_value_and_comma_lists(monkeypatch):
    cfg = openCGConfig.model_validate(
        {"ingestion": {"git": {"allowed_hosts": "git.internal", "local_roots": "/tmp, /srv/repos"}}}
    )
    assert cfg.ingestion.git.allowed_hosts == ["git.internal"]
    assert cfg.ingestion.git.local_roots == ["/tmp", "/srv/repos"]
