# chester/cli.py
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

import chess
from dotenv import load_dotenv

from .lichess import fetch_lichess_pgn, parse_game, mainline_moves, position_before_ply
from .chess_utils import parse_player
from .pipeline_v2 import build_ux_v2_data, side_name
from .render_web_v2 import write_web_v2

from .rhythm_pipeline import build_rhythm_data
from .render_rhythm import write_rhythm_html


def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


def ply_index_for(move_number: int, player: chess.Color) -> int:
    return 2 * (move_number - 1) + (0 if player == chess.WHITE else 1)


async def explain(args: argparse.Namespace) -> int:
    lichess_token = os.getenv("LICHESS_TOKEN")
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        eprint("Missing GEMINI_API_KEY (or GOOGLE_API_KEY) in environment/.env")
        return 2

    pgn = await fetch_lichess_pgn(args.lichess_game_id, lichess_token)
    game = parse_game(pgn)
    moves = mainline_moves(game)

    requested_player = parse_player(args.player)
    ply0 = ply_index_for(args.move_number, requested_player)
    if ply0 >= len(moves):
        raise RuntimeError(f"Requested move is beyond game length: ply {ply0} vs {len(moves)} plies")

    board_pre = position_before_ply(game, ply0)

    # Sanity correction if side-to-move mismatch
    corrected = False
    corrected_from = None
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
    eprint(f"Side to move: {side_name(board_pre.turn)}")
    eprint(f"Actual move played: {actual_san} ({actual_uci})\n")

    fen = board_pre.fen()

    ux = await build_ux_v2_data(
        fen=fen,
        board_pre=board_pre,
        actual_uci=actual_uci,
        actual_san=actual_san,
        depth=args.depth,
        eval_depth=args.eval_depth,
        pv_plies=args.pv_plies,
        multipv=args.multipv,
        modal_batch_size=args.modal_batch_size,
        quick_model=args.quick_model,
        smart_model=args.smart_model,
        llm_concurrency=args.llm_concurrency,
        llm_max_tokens_short=args.llm_max_tokens_short,
        llm_max_tokens_long=args.llm_max_tokens_long,
        quiet=args.quiet,
    )

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
        **ux,
    }

    html_path = write_web_v2(dist_dir=Path("dist"), data=data)
    eprint(f"Wrote {html_path}")
    eprint(f"LLM log (JSONL): {os.getenv('CHESTER_LLM_LOG', 'llm_log.jsonl')}")

    try:
        webbrowser.open(f"file://{html_path.resolve()}")
    except Exception:
        pass

    return 0


async def rhythm(args: argparse.Namespace) -> int:
    lichess_token = os.getenv("LICHESS_TOKEN")

    pgn = await fetch_lichess_pgn(args.lichess_game_id, lichess_token)
    color = parse_player(args.player)

    data = await build_rhythm_data(
        lichess_game_id=args.lichess_game_id,
        pgn=pgn,
        color=color,
        depth=args.depth,
        width=args.width,
        pv_plies=args.pv_plies,
        modal_batch_size=args.modal_batch_size,
        quiet=args.quiet,
    )

    out = write_rhythm_html(Path("dist"), data)
    eprint(f"Wrote {out}")

    try:
        webbrowser.open(f"file://{out.resolve()}")
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

    ex.add_argument("--multipv", type=int, default=4, help="N candidate engine moves (plus actual if different).")
    ex.add_argument("--modal-batch-size", type=int, default=3)

    ex.add_argument(
        "--llm-concurrency",
        type=int,
        default=24,
        help="Max number of parallel Gemini calls (high by design; adjust if rate-limited).",
    )

    # NEW: model selection
    ex.add_argument(
        "--quick-model",
        default="gemini-2.5-flash",
        help="Model used for per-position summaries (PV node cards).",
    )
    ex.add_argument(
        "--smart-model",
        default="gemini-2.5-pro",
        help="Model used for strategic analysis (starting position, line overall, comparisons).",
    )

    # token caps
    ex.add_argument(
        "--llm-max-tokens-short",
        type=int,
        default=900,
        help="Max output tokens for per-position summaries (starting position + PV node cards).",
    )
    ex.add_argument(
        "--llm-max-tokens-long",
        type=int,
        default=1600,
        help="Max output tokens for long-form analysis (line overall + line comparisons).",
    )

    ex.add_argument("--quiet", action="store_true")

    rh = sub.add_parser("rhythm")
    rh.add_argument("lichess_game_id")
    rh.add_argument("player", help="white|black")
    rh.add_argument("--depth", type=int, default=16, help="Max Stockfish depth (plies).")
    rh.add_argument("--width", type=int, default=4, help="MultiPV width per position.")
    rh.add_argument("--pv-plies", type=int, default=24, help="PV length requested per position.")
    rh.add_argument("--modal-batch-size", type=int, default=16, help="Batch size (positions per Modal call).")
    rh.add_argument("--quiet", action="store_true")

    args = p.parse_args()

    if args.cmd == "explain":
        return asyncio.run(explain(args))

    if args.cmd == "rhythm":
        return asyncio.run(rhythm(args))

    return 0
