from __future__ import annotations

import asyncio
import json
import os
import re
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google import genai

# optional .env (important when importing modules directly from main.py)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_LLM_LOG_PATH = os.getenv("CHESTER_LLM_LOG", "llm_log.jsonl")

# Lazily-created singleton client
_CLIENT: Optional[genai.Client] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_llm_log(entry: Dict[str, Any]) -> None:
    try:
        with open(_LLM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extract_json_obj(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def extract_json_obj(text: str) -> Optional[dict]:
    return _extract_json_obj(text)


def _get_client() -> genai.Client:
    """
    Create the genai.Client only when needed, with explicit credentials.
    Supports either:
      - Google AI API: api_key=...
      - Vertex AI: vertexai=True, project=..., location=...
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    # Prefer GEMINI_API_KEY, but accept GOOGLE_API_KEY too.
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # Optional Vertex config
    use_vertex = (os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes"))
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_LOCATION") or "us-central1"

    if use_vertex:
        if not project:
            raise ValueError(
                "Vertex AI selected (GOOGLE_GENAI_USE_VERTEXAI=1) but no project set. "
                "Set GOOGLE_CLOUD_PROJECT (or GOOGLE_PROJECT) and optionally GOOGLE_CLOUD_LOCATION."
            )
        _CLIENT = genai.Client(vertexai=True, project=project, location=location)
        return _CLIENT

    if not api_key:
        raise ValueError(
            "Missing API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment/.env. "
            "Alternatively set GOOGLE_GENAI_USE_VERTEXAI=1 with project/location for Vertex."
        )

    _CLIENT = genai.Client(api_key=api_key)
    return _CLIENT


async def gemini_text(
    prompt: str,
    *,
    model: str,
    temperature: float = 0.3,
    max_output_tokens: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
    retries: int = 5,
) -> str:
    """
    Calls Gemini and logs prompt/output as JSONL.
    Includes retry/backoff for transient errors (429/5xx-like).
    """

    def _call_once() -> str:
        client = _get_client()
        cfg: Dict[str, Any] = {"temperature": temperature}
        if max_output_tokens is not None:
            cfg["max_output_tokens"] = int(max_output_tokens)

        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=cfg,
            )
        except TypeError:
            # SDK signature fallback
            resp = client.models.generate_content(model=model, contents=prompt)
        return resp.text or ""

    ts = _now_iso()
    last_err: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            txt = await asyncio.to_thread(_call_once)
            _append_llm_log(
                {
                    "ts": ts,
                    "model": model,
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                    "meta": meta or {},
                    "prompt": prompt,
                    "output": txt,
                }
            )
            return txt
        except Exception as e:
            last_err = e
            _append_llm_log(
                {
                    "ts": ts,
                    "model": model,
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                    "meta": meta or {},
                    "prompt": prompt,
                    "error": str(e),
                    "attempt": attempt,
                }
            )
            if attempt >= retries:
                raise

            # Exponential backoff with jitter
            base = 0.75 * (2 ** attempt)
            jitter = random.random() * 0.4
            await asyncio.sleep(base + jitter)

    raise last_err or RuntimeError("gemini_text failed")


async def pick_llm_move(
    *,
    fen: str,
    side_to_move: str,
    pgn: str,
    ascii_board: str,
    legal_uci: list[str],
    model: str,
) -> Optional[str]:
    """
    Back-compat helper (not used in UX v2 default pipeline).
    """
    prompt = f"""You are a strong chess coach.

Return ONLY JSON.

Side to move: {side_to_move}
FEN: {fen}
ASCII (same position):
{ascii_board}

Choose the single best move for the side to move.

Output schema:
{{
  "move_uci": "e2e4",
  "short_reason": "one sentence max"
}}

PGN:
{pgn}

Legal moves (UCI):
{", ".join(legal_uci)}
"""
    txt = await gemini_text(
        prompt,
        model=model,
        temperature=0.2,
        max_output_tokens=200,
        meta={"stage": "pick_llm_move"},
    )
    obj = _extract_json_obj(txt)
    if not obj:
        return None
    uci = str(obj.get("move_uci") or "").strip()
    return uci or None
