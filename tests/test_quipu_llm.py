"""JobHawk's LLM provider = QUIPU's route (src/libs/quipu_llm.py)."""
import os
from pathlib import Path

import pytest

from src.libs import quipu_llm

FAKE_CALLER = '''
_OR_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
def _strip_think_tokens(text):
    return text.replace("<think>x</think>", "").strip()
def _resolve_backend_chain(decision):
    import os
    key = os.environ.get("FAKE_OR_KEY")
    return [{
        "name": "openrouter",
        "base_url": _OR_BASE_URL,
        "candidate_models": [decision.model_id or "openai/gpt-oss-20b:free", "openai/gpt-oss-120b:free"],
        "key_env": "OPENROUTER_API_KEY",
        "key": key,
        "extra_headers": {"HTTP-Referer": "https://supply-chain-architect.local",
                          "X-Title": "Supply Chain Architect DBI"},
    }]
'''


@pytest.fixture
def fake_caller(tmp_path, monkeypatch):
    path = tmp_path / "llm_caller_openrouter.py"
    path.write_text(FAKE_CALLER, encoding="utf-8")
    monkeypatch.setenv("QUIPU_LLM_CALLER", str(path))
    monkeypatch.setattr(quipu_llm, "_caller", None)
    monkeypatch.setattr(quipu_llm, "_caller_path", None)
    yield path
    quipu_llm._caller = None
    quipu_llm._caller_path = None


def test_no_key_is_unavailable_and_raises(fake_caller, monkeypatch):
    monkeypatch.delenv("FAKE_OR_KEY", raising=False)
    assert quipu_llm.is_available() is False
    st = quipu_llm.status()
    assert st["available"] is False and st["providers"][0]["key_live"] is False
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        quipu_llm.chat_model()


def test_chain_becomes_fallback_clients_in_quipu_order(fake_caller, monkeypatch):
    monkeypatch.setenv("FAKE_OR_KEY", "sk-or-test-0123456789")
    model = quipu_llm.chat_model("glm-5.1")
    primary = model.runnable
    fallbacks = list(model.fallbacks)
    assert primary.model_name == "glm-5.1"
    assert [f.model_name for f in fallbacks] == ["openai/gpt-oss-120b:free"]
    assert str(primary.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    assert primary.default_headers["X-Title"] == "Supply Chain Architect JobHawk"
    assert primary.default_headers["HTTP-Referer"] == "https://supply-chain-architect.local"


def test_status_never_contains_the_key(fake_caller, monkeypatch):
    monkeypatch.setenv("FAKE_OR_KEY", "sk-or-test-0123456789")
    assert "sk-or-test" not in repr(quipu_llm.status())


def test_strip_think_uses_quipu(fake_caller):
    assert quipu_llm.strip_think("<think>x</think> hello") == "hello"


@pytest.mark.skipif(
    not Path("/mesh/pipeline/src/brain/llm_caller_openrouter.py").is_file(),
    reason="QUIPU pipeline not mounted",
)
def test_real_quipu_caller_resolves_openrouter(monkeypatch):
    monkeypatch.delenv("QUIPU_LLM_CALLER", raising=False)
    quipu_llm._caller = None
    chain = quipu_llm.backend_chain("")
    assert chain[0]["name"] == "openrouter"
    assert chain[0]["candidate_models"], "QUIPU gave no models"
