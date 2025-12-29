from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

import chess
import chess.pgn
import httpx


async def fetch_lichess_pgn(game_id: str, token: Optional[str]) -> str:
    url = f"https://lichess.org/game/export/{game_id}"
    headers = {"Accept": "application/x-chess-pgn"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {"clocks": "true", "evals": "true", "opening": "true"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code != 200 or not r.text.strip():
            raise RuntimeError(f"Lichess export failed ({r.status_code}): {r.text[:200]}")
        return r.text


def parse_game(pgn_text: str) -> chess.pgn.Game:
    g = chess.pgn.read_game(io.StringIO(pgn_text))
    if not g:
        raise RuntimeError("Could not parse PGN from Lichess export.")
    return g


def mainline_moves(game: chess.pgn.Game) -> List[chess.Move]:
    moves = []
    node = game
    while node.variations:
        node = node.variations[0]
        moves.append(node.move)
    return moves


def mainline_nodes(game: chess.pgn.Game) -> List[chess.pgn.ChildNode]:
    nodes: List[chess.pgn.ChildNode] = []
    node = game
    while node.variations:
        node = node.variations[0]
        nodes.append(node)
    return nodes


def position_before_ply(game: chess.pgn.Game, ply_index_0: int) -> chess.Board:
    board = game.board()
    moves = mainline_moves(game)
    ply_index_0 = max(0, min(ply_index_0, len(moves)))
    for m in moves[:ply_index_0]:
        board.push(m)
    return board


@dataclass
class TimeControlInfo:
    base_seconds: int
    increment_seconds: int


_TC_RE = re.compile(r"^\s*(\d+)\s*(?:\+\s*(\d+)\s*)?$")
_CLK_TAG_RE = re.compile(r"\[%clk\s+([0-9]+(?::[0-9]{2}){1,2})\]")  # e.g. 5:00 or 0:05:00


def parse_timecontrol(tc: str) -> Optional[TimeControlInfo]:
    """
    Handles common Lichess headers: "600+0", "300+5", etc.
    Returns None if unsupported (e.g., "-" or "1/2" or unknown formats).
    """
    if not tc:
        return None
    tc = tc.strip()
    if tc in ("-", "?", "0"):
        return None
    m = _TC_RE.match(tc)
    if not m:
        return None
    base = int(m.group(1))
    inc = int(m.group(2) or 0)
    return TimeControlInfo(base_seconds=base, increment_seconds=inc)


def _hms_to_seconds(s: str) -> Optional[float]:
    """
    Accepts "M:SS" or "H:MM:SS".
    """
    try:
        parts = [int(x) for x in s.strip().split(":")]
        if len(parts) == 2:
            m, sec = parts
            return float(m * 60 + sec)
        if len(parts) == 3:
            h, m, sec = parts
            return float(h * 3600 + m * 60 + sec)
    except Exception:
        return None
    return None


def _extract_clk_from_comment(comment: str) -> Optional[float]:
    if not comment:
        return None
    m = _CLK_TAG_RE.search(comment)
    if not m:
        return None
    return _hms_to_seconds(m.group(1))


def extract_clock_series(
    game: chess.pgn.Game,
) -> Tuple[Optional[TimeControlInfo], List[Optional[float]], List[Optional[float]]]:
    """
    Returns:
      (time_control_info_or_none,
       white_time_left_seconds_by_ply (len = plies+1, index 0 is start),
       black_time_left_seconds_by_ply (len = plies+1, index 0 is start))

    Convention:
      - index 0 is starting time (base_seconds) for both if available
      - after ply i (1..N), the player who moved at that ply has a [%clk] clock recorded on the node comment;
        we store it at that ply index for that color.
    """
    tc_header = (game.headers.get("TimeControl") or "").strip()
    tci = parse_timecontrol(tc_header)

    nodes = mainline_nodes(game)
    nplies = len(nodes)

    w: List[Optional[float]] = [None] * (nplies + 1)
    b: List[Optional[float]] = [None] * (nplies + 1)

    if tci is not None:
        w[0] = float(tci.base_seconds)
        b[0] = float(tci.base_seconds)

    board = game.board()
    for ply_i, node in enumerate(nodes, start=1):
        mover = board.turn  # side to move before pushing

        # Prefer a direct clock parse from comment (robust for Lichess).
        clk = _extract_clk_from_comment(getattr(node, "comment", "") or "")

        # Fallback: python-chess helper (may be None depending on version/parser)
        if clk is None:
            try:
                clk_td = node.clock()
                if clk_td is not None:
                    clk = float(clk_td.total_seconds())
            except Exception:
                clk = None

        if mover == chess.WHITE:
            w[ply_i] = clk
        else:
            b[ply_i] = clk

        board.push(node.move)

    return tci, w, b
