from __future__ import annotations
import io
from typing import Optional, List

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

def position_before_ply(game: chess.pgn.Game, ply_index_0: int) -> chess.Board:
    board = game.board()
    moves = mainline_moves(game)
    ply_index_0 = max(0, min(ply_index_0, len(moves)))
    for m in moves[:ply_index_0]:
        board.push(m)
    return board
