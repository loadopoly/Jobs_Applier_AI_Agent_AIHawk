"""QUIPU's LLM route, used by JobHawk as its provider (2026-09-29).

JobHawk does not keep its own provider table. It loads QUIPU's caller,
pipeline/src/brain/llm_caller_openrouter.py, from the mounted pipeline tree
(/mesh/pipeline in the container) and asks it for the backend chain, so it
follows QUIPU's setup as that changes:

  * transport: OpenRouter, then direct xAI Grok when XAI_API_KEY is live
  * model: a canonical brain.yaml ID mapped through config/model_map.json
    (used while fresher than 48 h, else the caller's built-in map), or a raw
    vendor/slug; empty means QUIPU's default
  * fallbacks: QUIPU's fallback slug list, in order
  * key: OPENROUTER_API_KEY / XAI_API_KEY, pipeline/.env first, then the env

Only the request itself is JobHawk's: QUIPU's ensemble caller caps replies at
350 tokens with a 7 s timeout, which is too short for resume tailoring and
recruiter briefings, so requests go through langchain's ChatOpenAI against the
same base URL, key, headers and model order.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CALLER_REL = Path("src") / "brain" / "llm_caller_openrouter.py"

_caller: Optional[ModuleType] = None
_caller_path: Optional[Path] = None


def _candidate_paths() -> List[Path]:
    paths: List[Path] = []
    explicit = os.environ.get("QUIPU_LLM_CALLER", "").strip()
    if explicit:
        paths.append(Path(explicit))
    for root in (os.environ.get("QUIPU_PIPELINE_DIR", "").strip(), "/mesh/pipeline"):
        if root:
            paths.append(Path(root) / _CALLER_REL)
    # Host checkout: <VS Code>/Jobs_Applier_AI_Agent_AIHawk -> <VS Code>/pipeline
    paths.append(_REPO_ROOT.parent / "pipeline" / _CALLER_REL)
    return paths


def load_caller() -> ModuleType:
    """Import QUIPU's caller by file path (its package __init__ is not needed)."""
    global _caller, _caller_path
    if _caller is not None:
        return _caller
    for path in _candidate_paths():
        if path.is_file():
            spec = importlib.util.spec_from_file_location("quipu_llm_caller_openrouter", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            _caller, _caller_path = module, path
            return module
    tried = ", ".join(str(p) for p in _candidate_paths())
    raise RuntimeError(f"QUIPU LLM caller not found (tried: {tried})")


def backend_chain(model_id: str = "") -> List[Dict[str, Any]]:
    """QUIPU's provider chain for model_id: [{name, base_url, candidate_models,
    key_env, key, extra_headers}, ...]."""
    caller = load_caller()
    decision = SimpleNamespace(
        model_id=model_id or "",
        endpoint_env=os.environ.get("QUIPU_LLM_ENDPOINT_ENV", "").strip(),
    )
    return caller._resolve_backend_chain(decision)


def is_available(model_id: str = "") -> bool:
    """True when QUIPU's route has at least one live provider key."""
    try:
        return any(p.get("key") for p in backend_chain(model_id))
    except Exception:
        return False


def status(model_id: str = "") -> Dict[str, Any]:
    """Provider summary for /health. Never includes a key."""
    try:
        chain = backend_chain(model_id)
    except Exception as exc:
        return {"route": "quipu", "available": False, "error": str(exc)}
    return {
        "route": "quipu",
        "caller": str(_caller_path),
        "available": any(p.get("key") for p in chain),
        "providers": [
            {
                "name": p["name"],
                "key_env": p["key_env"],
                "key_live": bool(p.get("key")),
                "models": list(p["candidate_models"]),
            }
            for p in chain
        ],
    }


def strip_think(text: str) -> str:
    try:
        return load_caller()._strip_think_tokens(text)
    except Exception:
        return text


def chat_model(model_id: str = "", temperature: float = 0.4, timeout: float = 90.0):
    """A langchain chat model over QUIPU's chain: every live provider's
    candidate models, in QUIPU's order, as with_fallbacks()."""
    from langchain_openai import ChatOpenAI

    clients = []
    for provider in backend_chain(model_id):
        key = provider.get("key")
        if not key:
            continue
        base_url = provider["base_url"].rsplit("/chat/completions", 1)[0]
        headers = dict(provider.get("extra_headers") or {})
        if "X-Title" in headers:
            headers["X-Title"] = "Supply Chain Architect JobHawk"
        for model in provider["candidate_models"]:
            clients.append(
                ChatOpenAI(
                    model=model,
                    api_key=key,
                    base_url=base_url,
                    default_headers=headers or None,
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=2,
                )
            )
    if not clients:
        raise ValueError(
            "QUIPU LLM route has no live key: set OPENROUTER_API_KEY (or XAI_API_KEY) "
            "in the workspace .env or pipeline/.env"
        )
    return clients[0].with_fallbacks(clients[1:]) if len(clients) > 1 else clients[0]
