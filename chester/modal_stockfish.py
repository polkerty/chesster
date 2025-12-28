import os
import shutil
from typing import Any, Dict, List

import chess
import chess.engine
import modal

app = modal.App("chester-stockfish")

image = (
    modal.Image.debian_slim()
    .apt_install("stockfish")
    .pip_install("python-chess")
)

def _find_stockfish() -> str:
    path = shutil.which("stockfish")
    if path:
        return path
    for p in ("/usr/games/stockfish", "/usr/bin/stockfish"):
        if os.path.exists(p):
            return p
    raise RuntimeError("Stockfish not found in Modal image (unexpected).")

def _score_to_dict(score: chess.engine.PovScore) -> Dict[str, Any]:
    s = score.pov(chess.WHITE)  # normalize to White POV
    mate = s.mate()
    if mate is not None:
        return {"type": "mate", "mate": int(mate)}
    cp = s.score()
    return {"type": "cp", "cp": int(cp) if cp is not None else 0}

@app.function(image=image, timeout=600, cpu=2)
def top_engine_moves(
    fen: str,
    depth: int = 16,
    multipv: int = 3,
    pv_plies: int = 10,
) -> Dict[str, Any]:
    stockfish_path = _find_stockfish()
    board = chess.Board(fen)

    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        infos = engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=multipv,
            info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
        )
        if isinstance(infos, dict):
            infos = [infos]

        top = []
        for info in infos:
            pv = info.get("pv") or []
            if not pv:
                continue
            top.append(
                {
                    "move_uci": pv[0].uci(),
                    "score": _score_to_dict(info["score"]),
                    "pv_uci": [m.uci() for m in pv[: max(1, pv_plies)]],
                }
            )
        return {"top_moves": top}

@app.function(image=image, timeout=600, cpu=2)
def analyse_batch(
    fen: str,
    candidate_moves_uci: List[str],
    pv_plies: int = 10,
    depth: int = 16,
    eval_depth: int = 12,
) -> Dict[str, Any]:
    """
    For each candidate move, returns:
      root_score, pv_uci, positions=[{fen, score}...]
    positions includes start fen + after each pv ply.
    """
    stockfish_path = _find_stockfish()
    board = chess.Board(fen)

    out: Dict[str, Any] = {"candidates": {}}

    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        for uci in candidate_moves_uci:
            try:
                mv = chess.Move.from_uci(uci)
            except Exception:
                continue
            if mv not in board.legal_moves:
                continue

            info = engine.analyse(
                board,
                chess.engine.Limit(depth=depth),
                root_moves=[mv],
                info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
            )
            pv_moves = (info.get("pv") or [mv])[: max(1, pv_plies)]

            tmp = chess.Board(fen)
            fens = [tmp.fen()]
            for m in pv_moves:
                tmp.push(m)
                fens.append(tmp.fen())

            positions = []
            for f in fens:
                b = chess.Board(f)
                inf = engine.analyse(
                    b,
                    chess.engine.Limit(depth=eval_depth),
                    info=chess.engine.INFO_SCORE,
                )
                positions.append({"fen": f, "score": _score_to_dict(inf["score"])})

            out["candidates"][uci] = {
                "root_score": _score_to_dict(info["score"]),
                "pv_uci": [m.uci() for m in pv_moves],
                "positions": positions,
            }

    return out
