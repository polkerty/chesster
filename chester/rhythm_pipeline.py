# chester/rhythm_pipeline.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import chess

from .lichess import parse_game, mainline_moves, position_before_ply, extract_clock_series
from .modal_client import analyse_positions_modal_batched
from .pipeline_v2 import side_name

MATE_CP = 100000  # mate treated as huge cp for "gap" purposes


def _score_to_cp(score: Dict[str, Any]) -> int:
    if not score:
        return 0
    if score.get("type") == "mate":
        m = int(score.get("mate") or 0)
        if m == 0:
            return MATE_CP
        return MATE_CP if m > 0 else -MATE_CP
    return int(score.get("cp") or 0)


def _cp_to_pawns(cp: int) -> float:
    return float(cp) / 100.0


def _cap(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _sign_bucket(cp: int) -> int:
    if cp > 0:
        return 1
    if cp < 0:
        return -1
    return 0


def _perplexity_segments(cps_by_depth: List[int]) -> int:
    """
    Count #segments in sign sequence across depths.
    Example: W,W,W,B,W => 3
    """
    signs = [_sign_bucket(cp) for cp in cps_by_depth]

    # Carry forward last non-zero across zeros
    norm: List[int] = []
    last = 0
    for s in signs:
        if s == 0:
            norm.append(last)
        else:
            norm.append(s)
            last = s

    if all(s == 0 for s in norm):
        return 1

    seg = 0
    prev: Optional[int] = None
    for s in norm:
        if s == 0:
            continue
        if prev is None or s != prev:
            seg += 1
            prev = s
    return max(1, seg)


def _is_forced_from_topmoves(top_moves: List[Dict[str, Any]]) -> bool:
    if not top_moves or len(top_moves) < 2:
        return False
    cp1 = _score_to_cp((top_moves[0] or {}).get("score") or {})
    cp2 = _score_to_cp((top_moves[1] or {}).get("score") or {})
    return abs(cp1 - cp2) >= 100


def _best_pv_uci(top_moves: List[Dict[str, Any]]) -> List[str]:
    if not top_moves:
        return []
    pv = (top_moves[0] or {}).get("pv_uci") or []
    return [str(u) for u in pv if u]


def _fens_before_each_ply(game: chess.pgn.Game) -> List[str]:
    moves = mainline_moves(game)
    out: List[str] = []
    for ply0 in range(0, len(moves) + 1):
        b = position_before_ply(game, ply0)
        out.append(b.fen())
    return out


def _collect_pv_fens(root_fen: str, pv_uci: List[str], *, max_plies: int) -> List[str]:
    b = chess.Board(root_fen)
    out = [b.fen()]
    for u in pv_uci[: max_plies]:
        try:
            mv = chess.Move.from_uci(u)
        except Exception:
            break
        if mv not in b.legal_moves:
            break
        b.push(mv)
        out.append(b.fen())
    return out


async def _dist_to_forced_for_color(
    *,
    fens: List[str],
    best_pv_at_fen: Dict[str, List[str]],
    depth_max: int,
    modal_batch_size: int,
    quiet: bool,
    color: chess.Color,
    cap_moves: int = 6,
) -> List[int]:
    """
    For each root fen, walk best PV at deepest depth and find earliest position where:
      - it's `color` to move, and
      - that position is forced (gap >= 100cp between best and 2nd).
    Count result in "moves by `color`" (0 if forced immediately). Cap at cap_moves.
    """
    max_pv_plies = cap_moves * 2

    pv_fens_set = set()
    pv_fens_by_root: Dict[str, List[str]] = {}

    for fen in fens:
        pv = best_pv_at_fen.get(fen) or []
        pv_fens = _collect_pv_fens(fen, pv, max_plies=max_pv_plies)
        pv_fens_by_root[fen] = pv_fens
        pv_fens_set.update(pv_fens)

    pv_all = list(pv_fens_set)

    pv_forced_res = await analyse_positions_modal_batched(
        pv_all,
        depth=depth_max,
        multipv=2,
        pv_plies=1,
        modal_batch_size=int(modal_batch_size),
        quiet=quiet,
    )

    forced_pv: Dict[str, bool] = {}
    for fen in pv_all:
        top_moves = (pv_forced_res.get(fen) or {}).get("top_moves") or []
        forced_pv[fen] = _is_forced_from_topmoves(top_moves)

    dists: List[int] = []
    for fen in fens:
        pv_fens = pv_fens_by_root.get(fen) or [fen]
        moves_seen = 0
        found: Optional[int] = None

        for pf in pv_fens:
            b = chess.Board(pf)
            if b.turn == color:
                if forced_pv.get(pf, False):
                    found = moves_seen
                    break
                moves_seen += 1
                if moves_seen > cap_moves:
                    break

        if found is None:
            found = cap_moves
        dists.append(int(found))

    return dists


async def build_rhythm_data(
    *,
    lichess_game_id: str,
    pgn: str,
    color: chess.Color,  # still kept in meta; no longer affects polarity series
    depth: int,
    width: int,
    pv_plies: int,
    modal_batch_size: int,
    quiet: bool,
) -> Dict[str, Any]:
    game = parse_game(pgn)
    moves = mainline_moves(game)
    nplies = len(moves)

    fens = _fens_before_each_ply(game)

    # depths: 1,2,4,... <= depth
    depths: List[int] = []
    d = 1
    while d <= int(depth):
        depths.append(d)
        d *= 2
    if not depths:
        depths = [int(depth)]
    depth_max = max(depths)

    # timings
    tci, w_clocks, b_clocks = extract_clock_series(game)

    # multi-depth analysis for all positions
    by_depth: Dict[int, Dict[str, Any]] = {}
    for d in depths:
        res = await analyse_positions_modal_batched(
            fens,
            depth=d,
            multipv=max(2, int(width)),
            pv_plies=int(pv_plies),
            modal_batch_size=int(modal_batch_size),
            quiet=quiet,
        )
        by_depth[d] = res

    # best cp by depth per fen + best PV
    best_cp_by_fen: Dict[str, List[int]] = {}
    best_pv_at_fen: Dict[str, List[str]] = {}
    for fen in fens:
        cps: List[int] = []
        for d in depths:
            top_moves = (by_depth[d].get(fen) or {}).get("top_moves") or []
            cp = _score_to_cp(((top_moves[0] or {}).get("score") or {}) if top_moves else {})
            cps.append(cp)
        best_cp_by_fen[fen] = cps

        top_moves_deep = (by_depth[depth_max].get(fen) or {}).get("top_moves") or []
        best_pv_at_fen[fen] = _best_pv_uci(top_moves_deep)

    # forced-distance for both colors
    dist_white = await _dist_to_forced_for_color(
        fens=fens,
        best_pv_at_fen=best_pv_at_fen,
        depth_max=depth_max,
        modal_batch_size=modal_batch_size,
        quiet=quiet,
        color=chess.WHITE,
        cap_moves=6,
    )
    dist_black = await _dist_to_forced_for_color(
        fens=fens,
        best_pv_at_fen=best_pv_at_fen,
        depth_max=depth_max,
        modal_batch_size=modal_batch_size,
        quiet=quiet,
        color=chess.BLACK,
        cap_moves=6,
    )

    # series
    ply_labels = list(range(0, nplies + 1))
    eval_series: List[float] = []
    perplex_white: List[Optional[float]] = []
    perplex_black_m: List[Optional[float]] = []
    forced_white: List[Optional[float]] = []
    forced_black_m: List[Optional[float]] = []
    stm_series: List[str] = []

    for i, fen in enumerate(fens):
        b = chess.Board(fen)
        turn = b.turn
        stm_series.append(side_name(turn))

        cps = best_cp_by_fen[fen]
        cp_deep = cps[depths.index(depth_max)]
        eval_pawns = _cap(_cp_to_pawns(cp_deep), -6.0, 6.0)
        eval_series.append(eval_pawns)

        perp = min(int(_perplexity_segments(cps)), 6)
        fw = min(int(dist_white[i]), 6)
        fb = min(int(dist_black[i]), 6)

        # Split series: only populate the side-to-move’s value; the other side is null to create "gapped" lines
        if turn == chess.WHITE:
            perplex_white.append(float(perp))
            perplex_black_m.append(None)
            forced_white.append(float(fw))
            forced_black_m.append(None)
        else:
            perplex_white.append(None)
            perplex_black_m.append(-float(perp))
            forced_white.append(None)
            forced_black_m.append(-float(fb))

    # time series (black mirrored negative)
    time_white: List[Optional[float]] = []
    time_black: List[Optional[float]] = []
    for i in range(0, nplies + 1):
        tw = w_clocks[i] if i < len(w_clocks) else None
        tb = b_clocks[i] if i < len(b_clocks) else None
        time_white.append(tw if tw is not None else None)
        time_black.append((-tb) if tb is not None else None)

    color_name = "WHITE" if color == chess.WHITE else "BLACK"

    return {
        "title": f"Rhythm: {lichess_game_id} ({color_name})",
        "lichess_game_id": lichess_game_id,
        "color_arg": color_name,
        "meta": {
            "nplies": nplies,
            "depths": depths,
            "depth_max": depth_max,
            "width": int(width),
            "pv_plies": int(pv_plies),
            "time_control": {
                "raw": (game.headers.get("TimeControl") or "").strip(),
                "base_seconds": int(tci.base_seconds) if tci is not None else None,
                "increment_seconds": int(tci.increment_seconds) if tci is not None else None,
                "has_clocks": any(x is not None for x in w_clocks[1:]) or any(x is not None for x in b_clocks[1:]),
            },
        },
        "series": {
            "ply": ply_labels,
            "eval_pawns": eval_series,                      # [-6, 6]
            "perplexity_white": perplex_white,             # [0, 6] or null
            "perplexity_black_mirrored": perplex_black_m,  # [-6, 0] or null
            "forced_dist_white": forced_white,             # [0, 6] or null
            "forced_dist_black_mirrored": forced_black_m,  # [-6, 0] or null
            "time_white_sec": time_white,
            "time_black_sec_mirrored": time_black,
        },
        "debug": {
            "side_to_move": stm_series,
            "dist_white": dist_white,
            "dist_black": dist_black,
        },
    }
