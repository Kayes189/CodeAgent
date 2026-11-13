from codeagent.config import (
    DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, Settings, load_settings, save_settings,
)


def test_defaults_are_deepseek_v4_pro():
    s = Settings()
    assert s.base_url == DEEPSEEK_BASE_URL == "https://api.deepseek.com"
    assert s.model == DEEPSEEK_MODEL == "deepseek-v4-pro"
    assert s.budget_usd == 0.80
    assert s.thinking_enabled is False
    assert s.validate() == ["API key is empty."]


def test_validate_rejects_other_model():
    s = Settings(api_key="k", model="deepseek-chat")
    assert any("deepseek-v4-pro" in p for p in s.validate())


def test_validate_rejects_other_endpoint():
    s = Settings(api_key="k", base_url="https://dashscope.aliyuncs.com")
    assert any("DeepSeek" in p for p in s.validate())


def test_validate_rejects_over_ceiling_budget():
    s = Settings(api_key="k", budget_usd=1.5)
    assert any("Budget" in p for p in s.validate())


def test_save_load_roundtrip_no_plaintext_key(tmp_path, monkeypatch):
    # Redirect secure store to a temp dir so we don't touch the real one.
    import codeagent.secrets_store as ss
    monkeypatch.setattr(ss, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(ss, "_KEY_FILE", tmp_path / "cfg" / "apikey.bin")
    monkeypatch.setattr(ss, "_FALLBACK_FILE", tmp_path / "cfg" / "apikey.txt")
    path = tmp_path / "config.json"
    s = Settings(api_key="sk-secret", budget_usd=0.5)
    save_settings(s, path)
    # The JSON config must NOT contain the key.
    assert "sk-secret" not in path.read_text(encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.api_key == "sk-secret"
    assert loaded.budget_usd == 0.5
    assert loaded.model == DEEPSEEK_MODEL


def test_env_overrides(tmp_path, monkeypatch):
    import codeagent.secrets_store as ss
    monkeypatch.setattr(ss, "_KEY_FILE", tmp_path / "none.bin")
    monkeypatch.setattr(ss, "_FALLBACK_FILE", tmp_path / "none.txt")
    monkeypatch.setenv("CODEAGENT_API_KEY", "from-env")
    monkeypatch.setenv("CODEAGENT_BUDGET_USD", "0.25")
    s = load_settings(tmp_path / "missing.json")
    assert s.api_key == "from-env"
    assert s.budget_usd == 0.25


def test_pricing_defaults_match_professor():
    s = Settings()
    assert s.pricing["cached_input_per_million"] == 0.044
    assert s.pricing["uncached_input_per_million"] == 1.32
    assert s.pricing["output_per_million"] == 3.96
