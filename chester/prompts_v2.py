# chester/prompts_v2.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .chess_utils import score_to_str, fen_to_ascii


def load_prompts_txt(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def build_engine_choice_prompt(*, fen: str, side_to_move: str, candidates: List[Dict[str, Any]]) -> str:
    # candidates: [{move_san, move_uci, root_eval}]
    cand_lines = []
    for c in candidates:
        cand_lines.append(
            f"- {c.get('move_san')} ({c.get('move_uci')})  root_eval={score_to_str(c.get('root_eval') or {'type':'cp','cp':0})}"
        )
    return f"""You are a strong chess analyst.

Return ONLY JSON.

We have a starting position and a list of engine-considered candidate moves.

Starting position
Side to move: {side_to_move}
FEN: {fen}
ASCII:
{fen_to_ascii(fen)}

Candidates:
{chr(10).join(cand_lines)}

Task:
Pick the single engine-best move and give a short reason (one sentence).

Output schema:
{{
  "engine_move_uci": "e2e4",
  "engine_move_san": "e4",
  "short_reason": "one sentence max"
}}
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
    ctx = " ".join(context_moves_san) if context_moves_san else "(none)"
    eval_str = score_to_str(eval_dict or {"type": "cp", "cp": 0})

    return f"""You are a strong chess coach.

Write a SHORT position summary: 3–5 sentences, no more.

Goal:
Explain what matters in THIS position for the side to move:
- key threats / plans
- tactical issues if any
- what the eval implies in human terms

Position label: {label}

Context (moves leading here in the PV, SAN):
{ctx}

The immediate move that led here (SAN): {move_san_that_led_here or "(start of PV)"}

Side to move: {side_to_move}
Engine eval (White POV): {eval_str}

FEN: {fen}
ASCII:
{fen_to_ascii(fen)}
"""


def build_line_overall_prompt(
    *,
    prompts_txt: str,
    fen_start: str,
    side_to_move: str,
    candidate_move_san: str,
    root_eval: Dict[str, Any],
    pv_san: List[str],
    per_ply_summaries: List[Dict[str, str]],  # {label, move_san, summary}
) -> str:
    root_eval_str = score_to_str(root_eval or {"type": "cp", "cp": 0})
    pv_str = " ".join(pv_san) if pv_san else "(none)"

    blocks = []
    for i, p in enumerate(per_ply_summaries, start=1):
        blocks.append(
            f"""STEP {i}
Label: {p.get('label','')}
Move (SAN): {p.get('move_san','')}
Summary:
{p.get('summary','').strip()}
"""
        )

    extra = prompts_txt.strip()
    if extra:
        extra = "\n\nAdditional guidance (prompts.txt):\n" + extra

    return f"""You are a chess analyst. Be concise and concrete.

We are evaluating a candidate first move from a starting position, then the engine PV that follows.

Starting position:
Side to move: {side_to_move}
FEN: {fen_start}
ASCII:
{fen_to_ascii(fen_start)}

Candidate first move (SAN): {candidate_move_san}
Root engine eval (White POV): {root_eval_str}

PV (SAN):
{pv_str}

Below are short summaries of the ensuing positions along the PV:

{chr(10).join(blocks)}

Task:
Write a short "overall result" summary of this line: 6–9 sentences max.
Focus on consequences, key tradeoffs, and why the first move succeeds/fails.
Do NOT rehash every ply; we already show those.

{extra}
"""


def build_line_compare_prompt(
    *,
    target_label: str,
    target_move_san: str,
    target_overall: str,
    others: List[Dict[str, str]],  # {label, move_san, overall}
) -> str:
    other_blocks = []
    for o in others:
        other_blocks.append(
            f"""- {o.get('label','')} / {o.get('move_san','')}
{o.get('overall','').strip()}
"""
        )

    return f"""You are a chess analyst.

We have several candidate lines. Each has an "overall result" summary.

Target line:
Label: {target_label}
Starting move: {target_move_san}
Summary:
{(target_overall or "").strip()}

Other lines:
{chr(10).join(other_blocks) if other_blocks else "(none)"}

Task:
Explain what turned out differently for the target line compared to the others.
Be concise: 6–10 bullets max.
No fluff; focus on concrete differences (plans, tactics, endgame type, pawn structure, king safety, etc.).
"""


def build_global_overview_prompt(
    *,
    fen_start: str,
    side_to_move: str,
    engine_best_move_san: str,
    engine_best_reason: str,
    actual_move_san: str,
    lines_compact: List[Dict[str, Any]],
) -> str:
    """
    Global overview at the top of the UX.

    lines_compact items should include:
      - move_san
      - labels (list)
      - root_eval_str
      - final_eval_str
      - final_fen
      - final_summary (summary text for last node)
      - line_overall
      - line_compare
    """

    blocks: List[str] = []
    for l in lines_compact:
        labels = ", ".join(l.get("labels") or [])
        blocks.append(
            f"""LINE: {labels}
Start move: {l.get('move_san')}
Root eval: {l.get('root_eval_str')}
Final eval: {l.get('final_eval_str')}

Final position:
FEN: {l.get('final_fen')}
ASCII:
{fen_to_ascii(l.get('final_fen') or fen_start)}

Final-position summary:
{(l.get('final_summary') or "").strip()}

Line overall:
{(l.get('line_overall') or "").strip()}

Line differences (vs others):
{(l.get('line_compare') or "").strip()}
"""
        )

    return f"""You are a strong chess coach and analyst. You are writing the TOP-LEVEL overview for a chess position exploration UI.

Your job:
Synthesize the situation from:
- the starting position,
- the candidate lines and their endpoints,
- the final-position summaries,
- the line-overall and line-compare summaries.

Write an overview that helps the user understand:
1) What is ACTUALLY important in the position (plans, threats, structural themes).
2) Common misconceptions / tempting but wrong ideas.
3) Why the engine-preferred move matters (and what it prevents/creates).
4) If the "actual" move is present, what misunderstanding it likely reflects, and what it misses.
5) What the user should pay attention to when choosing among the candidate moves.

Constraints:
- Keep it tight: 10–14 sentences total.
- Be concrete (name key squares/files/pawn breaks/king safety motifs).
- Do NOT list every PV move; we already show those.
- Avoid hedging.

Starting position:
Side to move: {side_to_move}
FEN: {fen_start}
ASCII:
{fen_to_ascii(fen_start)}

Engine-preferred move: {engine_best_move_san}
Engine’s short reason: {engine_best_reason}

Actual move played (if known): {actual_move_san or "(unknown)"}

Candidate-line evidence:
{chr(10).join(blocks)}
"""
