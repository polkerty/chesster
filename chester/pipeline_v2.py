# chester/pipeline_v2.py
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple, Optional

import chess

from .async_utils import async_map_progress
from .chess_utils import score_to_str, material_summary
from .gemini import gemini_text, extract_json_obj
from .prompts_v2 import (
    build_engine_choice_prompt,
    build_starting_position_prompt,
    build_position_summary_prompt,
    build_line_overall_prompt,
    build_line_compare_prompt,
    load_prompts_txt,
)
from .modal_client import get_top_moves_modal, analyse_candidates_modal_batched


def side_name(c: chess.Color) -> str:
    return "WHITE" if c == chess.WHITE else "BLACK"


def _dedupe_preserve(xs: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in xs:
        if x in seen:
            continue
        out.append(x)
        seen.add(x)
    return out


def _pv_san_and_fens(fen: str, pv_uci: List[str]) -> Tuple[List[str], List[str]]:
    b = chess.Board(fen)
    sans: List[str] = []
    fens: List[str] = [b.fen()]
    for u in pv_uci:
        mv = chess.Move.from_uci(u)
        sans.append(b.san(mv))
        b.push(mv)
        fens.append(b.fen())
    return sans, fens


async def build_ux_v2_data(
    *,
    fen: str,
    board_pre: chess.Board,
    actual_uci: str,
    actual_san: str,
    depth: int,
    eval_depth: int,
    pv_plies: int,
    multipv: int,
    modal_batch_size: int,
    gemini_model: str,
    llm_concurrency: int,
    quiet: bool,
) -> Dict[str, Any]:
    """
    Produces the structured JSON for UX v2.
    Prompt counts:
      - 1: engine preferred move (LLM confirms + short reason)
      - 1: starting position analysis
      - N*K: per-position summaries (for positions after the first move in each line)
      - N: overall line analysis
      - N: line-vs-others comparison
    """
    # ---------------------------
    # ENGINE: get N candidate moves (multipv), plus ensure actual is included.
    # ---------------------------
    top_moves = await get_top_moves_modal(
        fen,
        depth=depth,
        multipv=max(1, multipv),
        pv_plies=pv_plies,
        quiet=quiet,
    )

    engine_candidates = [tm["move_uci"] for tm in top_moves if tm.get("move_uci")]
    candidates = _dedupe_preserve([actual_uci] + engine_candidates)

    # Build labels
    labels: Dict[str, List[str]] = {}
    for u in candidates:
        labels[u] = []
    labels.setdefault(actual_uci, [])
    if "actual" not in labels[actual_uci]:
        labels[actual_uci].append("actual")
    for i, tm in enumerate(top_moves, start=1):
        u = tm.get("move_uci")
        if not u:
            continue
        if u in labels:
            labels[u].append(f"engine#{i}")

    # ---------------------------
    # ENGINE: analyze each candidate with PV + eval snapshots
    # ---------------------------
    cand_data = await analyse_candidates_modal_batched(
        fen,
        candidates,
        modal_batch_size=modal_batch_size,
        pv_plies=pv_plies,
        depth=depth,
        eval_depth=eval_depth,
        quiet=quiet,
    )

    # Create per-line base objects
    lines: List[Dict[str, Any]] = []
    for uci in candidates:
        cd = cand_data.get(uci)
        if not cd:
            continue

        pv_uci = cd.get("pv_uci") or []
        pv_san, _ = _pv_san_and_fens(fen, pv_uci)

        # Candidate move SAN from starting board
        try:
            mv = chess.Move.from_uci(uci)
            cand_san = board_pre.san(mv)
        except Exception:
            cand_san = uci

        positions = cd.get("positions") or []  # [{fen, score}] includes start + after each PV ply
        # We’ll show summaries for positions[1:] (K positions = pv_plies)
        nodes: List[Dict[str, Any]] = []
        # Build SAN for each transition (move that led to positions[i])
        # positions[1] led by pv_san[0] (candidate move), positions[2] led by pv_san[1], etc.
        for idx in range(1, len(positions)):
            fen_i = positions[idx]["fen"]
            score_i = positions[idx]["score"]
            b_i = chess.Board(fen_i)

            move_san_that_led_here = pv_san[idx - 1] if (idx - 1) < len(pv_san) else ""
            label = (
                f"{', '.join(labels.get(uci, ['candidate']))} — {cand_san}"
                if idx == 1
                else f"Engine choice — {move_san_that_led_here}"
            )

            nodes.append(
                {
                    "idx": idx,
                    "label": label,
                    "fen": fen_i,
                    "side_to_move": side_name(b_i.turn),
                    "eval": score_i,
                    "eval_str": score_to_str(score_i),
                    "move_san": move_san_that_led_here,
                    "material": material_summary(b_i),
                    "summary": "",  # filled by LLM
                }
            )

        lines.append(
            {
                "move_uci": uci,
                "move_san": cand_san,
                "labels": labels.get(uci, ["candidate"]),
                "root_eval": cd.get("root_score"),
                "root_eval_str": score_to_str(cd.get("root_score") or {"type": "cp", "cp": 0}),
                "pv_uci": pv_uci,
                "pv_san": pv_san,
                "nodes": nodes,
                "line_overall": "",
                "line_compare": "",
            }
        )

    # Determine “engine #1” move (if present)
    engine_best_uci = top_moves[0]["move_uci"] if top_moves else (lines[0]["move_uci"] if lines else None)
    engine_best_line = next((l for l in lines if l["move_uci"] == engine_best_uci), None)
    best_move_san = engine_best_line["move_san"] if engine_best_line else (lines[0]["move_san"] if lines else "")
    best_eval = engine_best_line["root_eval"] if engine_best_line else (lines[0]["root_eval"] if lines else {"type": "cp", "cp": 0})

    # ---------------------------
    # LLM(1): engine preferred move confirmation + short reason
    # ---------------------------
    cand_for_llm = [
        {"move_san": l["move_san"], "move_uci": l["move_uci"], "root_eval": l["root_eval"] or {"type": "cp", "cp": 0}}
        for l in lines
    ]
    eng_pick_prompt = build_engine_choice_prompt(
        fen=fen,
        side_to_move=side_name(board_pre.turn),
        candidates=cand_for_llm,
    )
    eng_pick_txt = await gemini_text(
        eng_pick_prompt,
        model=gemini_model,
        temperature=0.2,
        max_output_tokens=250,
        meta={"stage": "engine_preferred_move"},
    )
    eng_pick_obj = extract_json_obj(eng_pick_txt) or {}
    engine_pick_reason = (str(eng_pick_obj.get("short_reason") or "")).strip()
    # Best effort: trust our engine_best if parsing fails
    engine_pick_move_uci = (str(eng_pick_obj.get("engine_move_uci") or "")).strip() or (engine_best_uci or "")
    engine_pick_move_san = (str(eng_pick_obj.get("engine_move_san") or "")).strip() or (best_move_san or "")

    # ---------------------------
    # LLM(1): starting position analysis
    # ---------------------------
    start_prompt = build_starting_position_prompt(
        fen=fen,
        side_to_move=side_name(board_pre.turn),
        best_eval=best_eval or {"type": "cp", "cp": 0},
        best_move_san=engine_pick_move_san,
        best_move_reason=engine_pick_reason or "(no reason returned)",
    )
    starting_summary = await gemini_text(
        start_prompt,
        model=gemini_model,
        temperature=0.25,
        max_output_tokens=450,
        meta={"stage": "starting_position"},
    )

    # ---------------------------
    # LLM(N*K): per-position summaries
    # ---------------------------
    # Key each node by (line_uci, node_idx)
    node_keys: List[Tuple[str, int]] = []
    node_map: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for l in lines:
        for n in l["nodes"]:
            k = (l["move_uci"], int(n["idx"]))
            node_keys.append(k)
            node_map[k] = n

    # Precompute PV context for each node (SAN prefix up to node)
    pv_context: Dict[Tuple[str, int], List[str]] = {}
    for l in lines:
        pv = l["pv_san"] or []
        for n in l["nodes"]:
            idx = int(n["idx"])
            # positions[idx] is after pv_san[idx-1], so include moves up to idx-1 inclusive
            pv_context[(l["move_uci"], idx)] = pv[: idx]

    async def _summarize_node(key: Tuple[str, int]) -> str:
        n = node_map[key]
        line_uci, idx = key
        # Find line
        line = next((x for x in lines if x["move_uci"] == line_uci), None)
        cand_move = line["move_san"] if line else line_uci

        prompt = build_position_summary_prompt(
            label=n["label"],
            fen=n["fen"],
            side_to_move=n["side_to_move"],
            eval_dict=n["eval"],
            move_san_that_led_here=n["move_san"],
            context_moves_san=pv_context.get(key, []),
        )
        return await gemini_text(
            prompt,
            model=gemini_model,
            temperature=0.25,
            max_output_tokens=350,
            meta={"stage": "per_ply_summary", "line_uci": line_uci, "node_idx": idx, "candidate": cand_move},
        )

    summaries_by_key = await async_map_progress(
        node_keys,
        _summarize_node,
        concurrency=llm_concurrency,
        desc=f"LLM per-ply summaries ({len(node_keys)})",
        quiet=quiet,
    )
    for k, txt in summaries_by_key.items():
        node_map[k]["summary"] = (txt or "").strip()

    # ---------------------------
    # LLM(N): line overall analysis (uses prompts.txt if present)
    # ---------------------------
    prompts_txt = load_prompts_txt("prompts.txt")

    async def _line_overall(uci: str) -> str:
        line = next(l for l in lines if l["move_uci"] == uci)
        per_ply = [
            {"label": n["label"], "move_san": n["move_san"], "summary": (n["summary"] or "").strip()}
            for n in line["nodes"]
        ]
        prompt = build_line_overall_prompt(
            prompts_txt=prompts_txt,
            fen_start=fen,
            side_to_move=side_name(board_pre.turn),
            candidate_move_san=line["move_san"],
            root_eval=line["root_eval"] or {"type": "cp", "cp": 0},
            pv_san=line["pv_san"] or [],
            per_ply_summaries=per_ply,
        )
        return await gemini_text(
            prompt,
            model=gemini_model,
            temperature=0.25,
            max_output_tokens=500,
            meta={"stage": "line_overall", "line_uci": uci, "move_san": line["move_san"]},
        )

    line_overall_by_uci = await async_map_progress(
        [l["move_uci"] for l in lines],
        _line_overall,
        concurrency=llm_concurrency,
        desc=f"LLM line overall ({len(lines)})",
        quiet=quiet,
    )
    for l in lines:
        l["line_overall"] = (line_overall_by_uci.get(l["move_uci"]) or "").strip()

    # ---------------------------
    # LLM(N): line comparisons vs others
    # ---------------------------
    async def _line_compare(uci: str) -> str:
        target = next(l for l in lines if l["move_uci"] == uci)
        others = [
            {"label": ", ".join(o["labels"]), "move_san": o["move_san"], "overall": o["line_overall"]}
            for o in lines
            if o["move_uci"] != uci
        ]
        prompt = build_line_compare_prompt(
            target_label=", ".join(target["labels"]),
            target_move_san=target["move_san"],
            target_overall=target["line_overall"],
            others=others,
        )
        return await gemini_text(
            prompt,
            model=gemini_model,
            temperature=0.25,
            max_output_tokens=450,
            meta={"stage": "line_compare", "line_uci": uci, "move_san": target["move_san"]},
        )

    line_compare_by_uci = await async_map_progress(
        [l["move_uci"] for l in lines],
        _line_compare,
        concurrency=llm_concurrency,
        desc=f"LLM line comparisons ({len(lines)})",
        quiet=quiet,
    )
    for l in lines:
        l["line_compare"] = (line_compare_by_uci.get(l["move_uci"]) or "").strip()

    # Package final data for render_web_v2
    data: Dict[str, Any] = {
        "starting": {
            "label": "Starting position",
            "fen": fen,
            "side_to_move": side_name(board_pre.turn),
            "eval_str": score_to_str(best_eval or {"type": "cp", "cp": 0}),
            "engine_preferred": {
                "move_uci": engine_pick_move_uci,
                "move_san": engine_pick_move_san,
                "reason": engine_pick_reason,
            },
            "summary": (starting_summary or "").strip(),
        },
        "lines": lines,
    }
    return data
