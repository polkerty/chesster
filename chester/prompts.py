from __future__ import annotations
from typing import Any, Dict, List

from .chess_utils import score_to_str, fen_to_ascii


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

    start_ascii = fen_to_ascii(fen_start)

    blocks_txt = []
    for i, b in enumerate(ply_blocks[:-1]):
        fen_i = b["fen"]
        blocks_txt.append(
            f"""PLY {i+1}
FEN: {fen_i}
ASCII:
{fen_to_ascii(fen_i)}
Material (W): {b['material']['values']['white']}  (B): {b['material']['values']['black']}  (W-B): {b['material']['delta']}
Engine eval (White POV): {score_to_str(b['eval'])}

--
Next move: {b['move_san']}

"""
        )

    final_fen = ply_blocks[-1]["fen"] if ply_blocks else fen_start
    final_mat = ply_blocks[-1]["material"] if ply_blocks else None
    final_eval = ply_blocks[-1]["eval"] if ply_blocks else root_eval

    if final_mat is None:
        # Shouldn't happen with current pipeline, but keep prompt stable.
        final_mat = {"values": {"white": 0, "black": 0}, "delta": 0}

    blocks_txt.append(
        f"""FINAL
FEN: {final_fen}
ASCII:
{fen_to_ascii(final_fen)}
Material (W): {final_mat['values']['white']}  (B): {final_mat['values']['black']}  (W-B): {final_mat['delta']}
Engine eval (White POV): {score_to_str(final_eval)}
"""
    )

    return f"""
Let's analyze a chess move. For context, we have a certain starting position,
and we want to take it as a given that a certain move is made (which may or may not be the best move).
From that point on, we use a chess engine to produce the principal variations.
So, we're trying to understand what happens when we make that particular
move in this context.

Use the voice of a dispassionate analyst.

Here is what I want you to do:
* Start by considering the initial position, the advantages/threats/tacticals/positional considerations, etc.
* Then look at the move that was made, and consider what might have motivated that move.
* Finally, review the principal variation after that point to explain the long-term consequences of that move,
how they develop into positional or material advantages/disadvantages, and tying back to how the original
move unlocked or failed to prevent etc. these developments.

Do all your analysis from the perspective of the player who is to move. Take into account
engine evals as appropriate, although we should expect to see no major swings after the first move,
since we are looking at an engine-generated principal line after that point.

Starting position:
Side to move: {side_to_move}
FEN: {fen_start} <-- before the first move is made
ASCII:
{start_ascii}

Line label(s): {label_str}
Candidate move: {candidate_move_san}

Engine eval at root (White POV): {root_eval_str}
Engine eval at end of PV (White POV): {final_eval_str}
  <-- keep in mind that if this value increases by a large amount, it implies that Black made the move at the beginning, and it was non-optimal;
      if it decreases by a large amount, it implies that White made the move at the beginning, and it was non-optimal.
      In any case, we tell you who made the first move above ("side to move"), but just to help connect the dots on what this means.
Line type: {classification}

What follows is a breakdown, ply by ply, of the first move (possibly non-optimal),
and then the engine-generated principal variation from that point on.

{''.join(blocks_txt)}
"""
