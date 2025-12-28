# chester/prompts_v2.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .chess_utils import fen_to_ascii, score_to_str


def build_engine_choice_prompt(
    *,
    fen: str,
    side_to_move: str,
    candidates: List[Dict[str, Any]],  # [{move_san, move_uci, root_eval}]
) -> str:
    cand_lines = "\n".join(
        f"- {c['move_san']} ({c['move_uci']}): {score_to_str(c['root_eval'])}"
        for c in candidates
    )

    return f"""You are a strong chess coach.

Return ONLY JSON.

We have a starting position and a set of candidate moves with engine root evals (White POV).
Pick the engine-preferred move (best eval for side-to-move; assume eval is White POV).
Then give a short, high-level reason (1-2 sentences).

Starting position:
Side to move: {side_to_move}
FEN: {fen}
ASCII:
{fen_to_ascii(fen)}

Candidates (SAN (UCI): eval):
{cand_lines}

Output schema:
{{
  "engine_move_uci": "e2e4",
  "engine_move_san": "e4",
  "short_reason": "1-2 sentences"
}}
"""


def build_starting_position_prompt(
    *,
    fen: str,
    side_to_move: str,
    best_eval: Dict[str, Any],
    best_move_san: str,
    best_move_reason: str,
) -> str:
    return f"""You are a chess analyst. Use a dispassionate, concise tone.

Task:
Write a brief (4-6 sentences) “main considerations” summary for the *current position*.
Do NOT enumerate long variations. Focus on: king safety, tactics, key squares, plans, and immediate threats.

Starting position:
Side to move: {side_to_move}
Engine best move: {best_move_san}
Engine eval (White POV): {score_to_str(best_eval)}
Engine reason (short):
{best_move_reason}

FEN: {fen}
ASCII:
{fen_to_ascii(fen)}
"""


def build_position_summary_prompt(
    *,
    label: str,
    fen: str,
    side_to_move: str,
    eval_dict: Dict[str, Any],
    move_san_that_led_here: str,
    context_moves_san: List[str],
) -> str:
    ctx = " ".join(context_moves_san[-10:]) if context_moves_san else ""
    mv = move_san_that_led_here or "(start)"

    return f"""You are a chess analyst. Use a dispassionate, concise tone.

Task:
Write a brief (3-5 sentences) “main considerations” summary for THIS position.
Focus on what matters *right now* for the side to move: threats, tactics, structural features, plans.
Avoid move-by-move narration.

Label: {label}
Move that led here: {mv}
PV context (SAN, last ~10 plies): {ctx}

Side to move: {side_to_move}
Engine eval (White POV): {score_to_str(eval_dict)}

FEN: {fen}
ASCII:
{fen_to_ascii(fen)}
"""


def load_prompts_txt(path: str = "prompts.txt") -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
        return s or None
    except Exception:
        return None


def build_line_overall_prompt(
    *,
    prompts_txt: Optional[str],
    fen_start: str,
    side_to_move: str,
    candidate_move_san: str,
    root_eval: Dict[str, Any],
    pv_san: List[str],
    per_ply_summaries: List[Dict[str, str]],  # [{label, move_san, summary}]
) -> str:
    # Compact summary block to feed the “overall line analysis”
    ply_block = "\n".join(
        f"- {p['label']} :: {p['move_san']}\n  {p['summary']}".strip()
        for p in per_ply_summaries
    )

    base = f"""You are a chess analyst. Use a dispassionate, concise tone.

We are evaluating a candidate first move from a starting position, then the engine PV.
You have already produced short per-position summaries for each ply in the PV.

Goal:
Provide a SHORT overall assessment (6-10 sentences max):
- What the initial move aims for
- What the engine reply sequence achieves
- What the main consequence is (tactical/positional/material/king safety)
- Whether the move seems strong/okay/inaccurate for the side to move, and why
Do NOT rehash every ply (those are already shown above).

Starting position:
Side to move: {side_to_move}
FEN: {fen_start}
ASCII:
{fen_to_ascii(fen_start)}

Candidate first move: {candidate_move_san}
Engine root eval (White POV): {score_to_str(root_eval)}
PV (SAN): {" ".join(pv_san)}

Per-ply summaries (in order):
{ply_block}
"""

    # If you have a custom prompts.txt, we prepend it as “system-style” instructions.
    # Keep it simple: prompts.txt can just be extra guidance text.
    if prompts_txt:
        return f"""{prompts_txt}

---

{base}
"""
    return base


def build_line_compare_prompt(
    *,
    target_label: str,
    target_move_san: str,
    target_overall: str,
    others: List[Dict[str, str]],  # [{label, move_san, overall}]
) -> str:
    other_txt = "\n\n".join(
        f"""LINE: {o['label']}
Move: {o['move_san']}
Overall:
{o['overall']}"""
        for o in others
    )

    return f"""You are a chess analyst. Use a dispassionate, concise tone.

Task:
Compare the TARGET line vs the OTHER lines.
Write 5-10 bullet points max (short bullets).
Focus on what turned out differently due to the starting move:
- changes in pawn structure, piece activity, king safety, tactics
- key traded pieces or key squares
- why the eval diverged (if it did)

TARGET:
Label: {target_label}
Move: {target_move_san}
Overall:
{target_overall}

OTHER LINES:
{other_txt}
"""
