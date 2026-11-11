from __future__ import annotations

from opencg_shared.config import load_config


def test_load_default_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENCG_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.tenant == "default"
    assert cfg.identity.principal == "local-dev"


def test_yaml_overrides_default(tmp_path, monkeypatch):
    cfg_file = tmp_path / "opencg.yaml"
    cfg_file.write_text("tenant: acme\nidentity:\n  principal: alice\n  roles: [admin]\n")
    cfg = load_config(cfg_file)
    assert cfg.tenant == "acme"
    assert cfg.identity.principal == "alice"
    assert cfg.identity.roles == ["admin"]


def test_env_overrides_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "opencg.yaml"
    cfg_file.write_text("tenant: acme\n")
    monkeypatch.setenv("OPENCG__TENANT", "globex")
    monkeypatch.setenv("OPENCG__IDENTITY__PRINCIPAL", "bob")
    monkeypatch.setenv("OPENCG__IDENTITY__ROLES", "admin,auditor")
    cfg = load_config(cfg_file)
    assert cfg.tenant == "globex"
    assert cfg.identity.principal == "bob"
    assert cfg.identity.roles == ["admin", "auditor"]


def test_legacy_ollama_populates_provider_defaults(tmp_path, monkeypatch):
    cfg_file = tmp_path / "opencg.yaml"
    cfg_file.write_text(
        "ollama:\n"
        "  base_url: http://local-ollama:11434\n"
        "  embedding_model: qwen3-embedding\n"
        "  api_key: legacy-embedding-key\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.providers.embeddings is not None
    assert cfg.providers.embeddings.base_url == "http://local-ollama:11434"
    assert cfg.providers.embeddings.model == "qwen3-embedding"
    assert cfg.providers.embeddings.api_key == "legacy-embedding-key"
    assert cfg.providers.chat is not None
    assert cfg.providers.chat.base_url == "http://local-ollama:11434"
    assert cfg.providers.chat.model == "gemma3:4b"
    assert cfg.providers.chat.api_key is None


def test_chat_provider_env_overrides(tmp_path, monkeypatch):
    cfg_file = tmp_path / "opencg.yaml"
    cfg_file.write_text(
        "providers:\n"
        "  chat:\n"
        "    provider: ollama\n"
        "    base_url: https://ollama.com\n"
        "    model: gemma3:4b\n"
    )
    monkeypatch.setenv("OPENCG__PROVIDERS__CHAT__MODEL", "kimi-k2")
    monkeypatch.setenv("OPENCG__PROVIDERS__CHAT__API_KEY", "cloud-key")
    cfg = load_config(cfg_file)
    assert cfg.providers.chat is not None
    assert cfg.providers.chat.model == "kimi-k2"
    assert cfg.providers.chat.api_key == "cloud-key"
