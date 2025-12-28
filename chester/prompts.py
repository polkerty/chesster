from __future__ import annotations
from typing import Any, Dict, List

import chess

from .chess_utils import material_summary, score_to_str

def build_line_prompt(
    *,
    label_str: str,
    fen_start: str,
    side_to_move: str,
    candidate_move_san: str,
    root_eval: Dict[str, Any],
    classification: str,
    ply_blocks: List[Dict[str, Any]],  # each: {fen, move_san, eval, material}
) -> str:
    root_eval_str = score_to_str(root_eval)
    final_eval_str = score_to_str(ply_blocks[-1]["eval"]) if ply_blocks else root_eval_str

    blocks_txt = []
    for i, b in enumerate(ply_blocks[:-1]):
        blocks_txt.append(
            f"""PLY {i+1}
FEN: {b['fen']}
Next move (SAN): {b['move_san']}
Material (W): {b['material']['values']['white']}  (B): {b['material']['values']['black']}  (W-B): {b['material']['delta']}
Engine eval (White POV): {score_to_str(b['eval'])}
"""
        )

    blocks_txt.append(
        f"""FINAL
FEN: {ply_blocks[-1]['fen']}
Material (W): {ply_blocks[-1]['material']['values']['white']}  (B): {ply_blocks[-1]['material']['values']['black']}  (W-B): {ply_blocks[-1]['material']['delta']}
Engine eval (White POV): {score_to_str(ply_blocks[-1]['eval'])}
"""
    )

    return f"""You are a chess coach writing an instructive, concise explanation.

Starting position:
Side to move: {side_to_move}
FEN: {fen_start}

Line label(s): {label_str}
Candidate move: {candidate_move_san}

Engine eval at root (White POV): {root_eval_str}
Engine eval at end of PV (White POV): {final_eval_str}
Line type: {classification}

Task:
Explain the value of choosing the candidate move.
- Explicitly reference the engine evals (root vs end, and any key swing).
- Explain the core idea in human terms (plan, target, king safety, tactics).
- If the line is tactical, identify the concrete tactic and what was missed.
- Give 2–3 bullet heuristics for similar positions.

Data:
{''.join(blocks_txt)}
"""
