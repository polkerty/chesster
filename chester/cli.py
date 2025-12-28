# chester/cli.py
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import chess
from dotenv import load_dotenv
from tqdm import tqdm

from .lichess import fetch_lichess_pgn, parse_game, mainline_moves, position_before_ply
from .chess_utils import (
    parse_player,
    score_to_str,
    material_summary,
    is_tactics_line,
)
from .gemini import pick_llm_move, gemini_text
from .prompts import build_line_prompt
from .modal_client import get_top_moves_modal, analyse_candidates_modal_batched
from .render_web import write_web


def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


def ply_index_for(move_number: int, player: chess.Color) -> int:
    return 2 * (move_number - 1) + (0 if player == chess.WHITE else 1)


def side_name(c: chess.Color) -> str:
    return "WHITE" if c == chess.WHITE else "BLACK"


async def explain(args: argparse.Namespace) -> int:
    lichess_token = os.getenv("LICHESS_TOKEN")
    gemini_model = args.gemini_model

    pgn = await fetch_lichess_pgn(args.lichess_game_id, lichess_token)
    game = parse_game(pgn)
    moves = mainline_moves(game)

    requested_player = parse_player(args.player)
    ply0 = ply_index_for(args.move_number, requested_player)

    if ply0 >= len(moves):
        raise RuntimeError(
            f"Requested move is beyond game length: ply {ply0} vs {len(moves)} plies"
        )

    board_pre = position_before_ply(game, ply0)

    corrected = False
    corrected_from = None

    # Sanity fix: if board_pre.turn doesn't match requested_player, try +/- 1
    if board_pre.turn != requested_player:
        for delta in (-1, +1):
            alt = ply0 + delta
            if 0 <= alt < len(moves):
                b_alt = position_before_ply(game, alt)
                if b_alt.turn == requested_player:
                    corrected = True
                    corrected_from = ply0
                    ply0 = alt
                    board_pre = b_alt
                    break

    actual_move = moves[ply0]
    actual_uci = actual_move.uci()
    actual_san = board_pre.san(actual_move)

    eprint(f"\nGame: {args.lichess_game_id}")
    eprint(f"Analyzing position BEFORE {args.player} move {args.move_number} (ply {ply0})")
    if corrected:
        eprint(f"⚠ sanity-corrected ply index: {corrected_from} → {ply0}")
    eprint(f"Side to move (should match request): {side_name(board_pre.turn)}")
    eprint(f"Actual move played: {actual_san} ({actual_uci})\n")

    fen = board_pre.fen()

    # LLM preferred move (single call)
    legal_uci = [m.uci() for m in board_pre.legal_moves]
    llm_uci = await pick_llm_move(
        fen=fen,
        side_to_move=side_name(board_pre.turn),
        pgn=pgn,
        ascii_board=str(board_pre),  # OK for move-pick; webpage renders via JS
        legal_uci=legal_uci,
        model=gemini_model,
    )

    # Top 3 engine moves (single modal call)
    top_moves = await get_top_moves_modal(
        fen,
        depth=args.depth,
        multipv=3,
        pv_plies=args.pv_plies,
        quiet=args.quiet,
    )

    # Candidate set + labels
    labels: Dict[str, Set[str]] = {}
    labels.setdefault(actual_uci, set()).add("actual")
    if llm_uci and llm_uci in legal_uci:
        labels.setdefault(llm_uci, set()).add("llm")

    for i, tm in enumerate(top_moves[:3], start=1):
        labels.setdefault(tm["move_uci"], set()).add(f"engine#{i}")

    candidates = list(labels.keys())

    # Modal batching + parallel calls
    cand_data = await analyse_candidates_modal_batched(
        fen,
        candidates,
        modal_batch_size=args.modal_batch_size,
        pv_plies=args.pv_plies,
        depth=args.depth,
        eval_depth=args.eval_depth,
        quiet=args.quiet,
    )

    # ----------------------------
    # Parallel Gemini per-line analysis
    # ----------------------------
    sem = asyncio.Semaphore(max(1, args.llm_concurrency))

    async def explain_one_line(uci: str) -> Tuple[str, Dict[str, Any]]:
        async with sem:
            try:
                data = cand_data[uci]
                pv_uci = data["pv_uci"]
                positions = data["positions"]  # list {fen, score}, start+...

                fens = [p["fen"] for p in positions]

                # Build SAN list + ply blocks with material + eval (NO SVG)
                ply_blocks = []
                pv_san = []
                for i in range(len(positions) - 1):
                    b = chess.Board(positions[i]["fen"])
                    mv = chess.Move.from_uci(pv_uci[i])
                    mv_san = b.san(mv)
                    pv_san.append(mv_san)
                    ply_blocks.append(
                        {
                            "fen": positions[i]["fen"],
                            "move_san": mv_san,
                            "eval": positions[i]["score"],
                            "material": material_summary(b),
                            "eval_str": score_to_str(positions[i]["score"]),
                        }
                    )

                # Final block
                b_final = chess.Board(positions[-1]["fen"])
                ply_blocks.append(
                    {
                        "fen": positions[-1]["fen"],
                        "move_san": "",
                        "eval": positions[-1]["score"],
                        "material": material_summary(b_final),
                        "eval_str": score_to_str(positions[-1]["score"]),
                    }
                )

                cand_move = chess.Move.from_uci(uci)
                cand_san = board_pre.san(cand_move)
                classification = "tactics" if is_tactics_line(fen, fens) else "positional"

                prompt = build_line_prompt(
                    label_str=", ".join(sorted(labels[uci])),
                    fen_start=fen,
                    side_to_move=side_name(board_pre.turn),
                    candidate_move_san=cand_san,
                    root_eval=data["root_score"],
                    classification=classification,
                    ply_blocks=ply_blocks,
                )

                explanation = await gemini_text(prompt, model=gemini_model, temperature=0.35)

                line_out = {
                    "move_uci": uci,
                    "move_san": cand_san,
                    "labels": sorted(labels[uci]),
                    "classification": classification,
                    "root_eval": data["root_score"],
                    "root_eval_str": score_to_str(data["root_score"]),
                    "pv_uci": pv_uci,
                    "pv_san": pv_san,
                    "start_fen": positions[0]["fen"],
                    "end_fen": positions[-1]["fen"],
                    "ply": ply_blocks,
                    "explanation": (explanation or "").strip(),
                }
                return uci, line_out
            except Exception as ex:
                # Keep pipeline alive; capture error
                cand_san = uci
                try:
                    cand_move = chess.Move.from_uci(uci)
                    if cand_move in board_pre.legal_moves:
                        cand_san = board_pre.san(cand_move)
                except Exception:
                    pass

                return (
                    uci,
                    {
                        "move_uci": uci,
                        "move_san": cand_san,
                        "labels": sorted(labels.get(uci, {"candidate"})),
                        "classification": "unknown",
                        "root_eval": {"type": "cp", "cp": 0},
                        "root_eval_str": "+0.00",
                        "pv_uci": [],
                        "pv_san": [],
                        "start_fen": fen,
                        "end_fen": fen,
                        "ply": [],
                        "explanation": "",
                        "error": str(ex),
                    },
                )

    tasks = [asyncio.create_task(explain_one_line(uci)) for uci in candidates]

    results_by_uci: Dict[str, Dict[str, Any]] = {}
    pbar = tqdm(total=len(tasks), disable=args.quiet, desc="Gemini line explanations")

    for fut in asyncio.as_completed(tasks):
        uci, line_out = await fut
        results_by_uci[uci] = line_out
        pbar.update(1)

    pbar.close()

    # Deterministic ordering: original candidate order
    lines_out: List[Dict[str, Any]] = [
        results_by_uci[uci] for uci in candidates if uci in results_by_uci
    ]

    # Meta explanation (single call)
    meta_prompt = "You are a chess coach...\n\n" + "\n\n".join(
        f"""LINE: {", ".join(l["labels"])}
Move: {l["move_san"]} root {l["root_eval_str"]}
PV: {" ".join(l["pv_san"])}
Explanation:
{l["explanation"]}
"""
        for l in lines_out
    )
    overall = await gemini_text(meta_prompt, model=gemini_model, temperature=0.35)

    # Terminal output (compact)
    print("\n=== CANDIDATES ===\n")
    for l in lines_out:
        err = f"  [ERROR: {l['error']}]" if "error" in l else ""
        print(
            f"[{', '.join(l['labels'])}] {l['move_san']}  root={l['root_eval_str']}  ({l['classification']}){err}"
        )
        if l["pv_san"]:
            print(f"PV: {' '.join(l['pv_san'])}")
        if l["explanation"]:
            print(l["explanation"])
        print("-" * 80)

    print("\n=== OVERALL ===\n")
    print((overall or "").strip())
    print()

    # Web output: single HTML with embedded JSON
    data = {
        "title": f"{args.lichess_game_id}: before {args.player} {args.move_number}",
        "side_to_move": side_name(board_pre.turn),
        "request": {
            "lichess_game_id": args.lichess_game_id,
            "player": args.player,
            "move_number": args.move_number,
            "ply_index": ply0,
            "corrected": corrected,
            "corrected_from": corrected_from,
        },
        "initial": {"fen": fen},
        "overall_explanation": (overall or "").strip(),
        "lines": lines_out,
    }

    html_path = write_web(dist_dir=Path("dist"), data=data)
    eprint(f"Wrote {html_path}")
    try:
        webbrowser.open(f"file://{html_path.resolve()}")
    except Exception:
        pass

    return 0


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="chester")
    sub = p.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("explain")
    ex.add_argument("lichess_game_id")
    ex.add_argument("move_number", type=int)
    ex.add_argument("player", help="white|black")

    ex.add_argument("--pv-plies", type=int, default=10)
    ex.add_argument("--depth", type=int, default=16)
    ex.add_argument("--eval-depth", type=int, default=12)
    ex.add_argument("--modal-batch-size", type=int, default=3)
    ex.add_argument(
        "--llm-concurrency",
        type=int,
        default=6,
        help="Max number of parallel Gemini calls for line explanations.",
    )

    ex.add_argument("--gemini-model", default="gemini-2.5-flash")
    ex.add_argument("--quiet", action="store_true")

    args = p.parse_args()

    if args.cmd == "explain":
        if not os.getenv("GEMINI_API_KEY"):
            eprint("Missing GEMINI_API_KEY in environment/.env")
            return 2
        return asyncio.run(explain(args))

    return 0
