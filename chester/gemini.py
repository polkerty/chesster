from __future__ import annotations
import asyncio
import json
import re
from typing import Any, Dict, Optional

from google import genai

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

async def gemini_text(prompt: str, model: str, temperature: float = 0.3) -> str:
    client = genai.Client()

    def _call() -> str:
        resp = client.models.generate_content(model=model, contents=prompt)
        return resp.text or ""

    return await asyncio.to_thread(_call)

async def pick_llm_move(
    *,
    fen: str,
    side_to_move: str,
    pgn: str,
    ascii_board: str,
    legal_uci: list[str],
    model: str,
) -> Optional[str]:
    prompt = f"""You are a strong chess coach.

Return ONLY JSON.

Side to move: {side_to_move}
FEN: {fen}

Choose the single best move for the side to move.

Output schema:
{{
  "move_uci": "e2e4",
  "short_reason": "one sentence max"
}}

PGN:
{pgn}

Board:
{ascii_board}

Legal moves (UCI):
{", ".join(legal_uci)}
"""
    txt = await gemini_text(prompt, model=model, temperature=0.2)
    obj = _extract_json_obj(txt)
    if not obj:
        return None
    uci = str(obj.get("move_uci") or "").strip()
    return uci or None
