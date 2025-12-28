from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Tuple

import modal

from .modal_stockfish import app as modal_app
from .modal_stockfish import top_engine_moves as modal_top_engine_moves
from .modal_stockfish import analyse_batch as modal_analyse_batch

from .chess_utils import chunked

async def get_top_moves_modal(
    fen: str,
    *,
    depth: int,
    multipv: int,
    pv_plies: int,
    quiet: bool,
) -> List[Dict[str, Any]]:
    with modal.enable_output(show_progress=not quiet):
        with modal_app.run():
            res = await asyncio.to_thread(
                lambda: modal_top_engine_moves.remote(fen, depth=depth, multipv=multipv, pv_plies=pv_plies)
            )
    return res.get("top_moves", [])

async def analyse_candidates_modal_batched(
    fen: str,
    candidates_uci: List[str],
    *,
    modal_batch_size: int,
    pv_plies: int,
    depth: int,
    eval_depth: int,
    quiet: bool,
) -> Dict[str, Any]:
    """
    Runs multiple modal calls in parallel, each with up to modal_batch_size moves.
    Returns merged dict: {uci: candidate_data}
    """
    batches = chunked(candidates_uci, max(1, modal_batch_size))

    async def run_one(batch: List[str]) -> Dict[str, Any]:
        return await asyncio.to_thread(
            lambda: modal_analyse_batch.remote(
                fen,
                batch,
                pv_plies=pv_plies,
                depth=depth,
                eval_depth=eval_depth,
            )
        )

    merged: Dict[str, Any] = {}

    with modal.enable_output(show_progress=not quiet):
        with modal_app.run():
            tasks = [asyncio.create_task(run_one(b)) for b in batches]
            for t in await asyncio.gather(*tasks):
                merged.update(t.get("candidates", {}))

    return merged
