# chester/chess_utils.py
from __future__ import annotations

from typing import Any, Dict, List

import chess

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
PIECE_NAMES = {
    chess.PAWN: "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}


def parse_player(s: str) -> chess.Color:
    s = s.strip().lower()
    if s in ("w", "white"):
        return chess.WHITE
    if s in ("b", "black"):
        return chess.BLACK
    raise ValueError("player must be 'white' or 'black'")


def score_to_str(score: Dict[str, Any]) -> str:
    if score.get("type") == "mate":
        return f"M{int(score['mate']):+d}"
    return f"{(int(score.get('cp', 0)) / 100):+.2f}"


def material_summary(board: chess.Board) -> Dict[str, Any]:
    counts = {
        "white": {k: 0 for k in ["P", "N", "B", "R", "Q", "K"]},
        "black": {k: 0 for k in ["P", "N", "B", "R", "Q", "K"]},
    }
    values = {"white": 0, "black": 0}

    for _, piece in board.piece_map().items():
        side = "white" if piece.color == chess.WHITE else "black"
        name = PIECE_NAMES[piece.piece_type]
        counts[side][name] += 1
        values[side] += PIECE_VALUES[piece.piece_type]

    return {"counts": counts, "values": values, "delta": values["white"] - values["black"]}


def is_tactics_line(start_fen: str, fens: List[str]) -> bool:
    start = chess.Board(start_fen)
    start_delta = material_summary(start)["delta"]
    for f in fens:
        if material_summary(chess.Board(f))["delta"] != start_delta:
            return True
    return False


def chunked(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i : i + n] for i in range(0, len(xs), n)]


# ---------------------------------------------------------------------------
# ASCII board helpers (coordinate-labeled) for LLM prompts & debugging.
# ---------------------------------------------------------------------------

def board_to_ascii(board: chess.Board) -> str:
    """
    Returns a coordinate-labeled ASCII board (8->1, a->h).
    Uses python-chess piece symbols: P/N/B/R/Q/K for White, lowercase for Black, '.' for empty.
    """
    files = "abcdefgh"
    header = "  " + " ".join(files)
    lines: List[str] = [header]
    for rank in range(7, -1, -1):
        row = [str(rank + 1)]
        for file in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            row.append(piece.symbol() if piece else ".")
        row.append(str(rank + 1))
        lines.append(" ".join(row))
    lines.append(header)
    return "\n".join(lines)


def fen_to_ascii(fen: str) -> str:
    """
    Convenience wrapper: parse FEN and render coordinate-labeled ASCII board.
    """
    b = chess.Board(fen)
    return board_to_ascii(b)
