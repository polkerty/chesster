# chester/render_web.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_web(dist_dir: Path, data: Dict[str, Any]) -> Path:
    """
    Writes a single self-contained HTML file:
      - embeds JSON inline (no CORS / fetch issues on file://)
      - uses chessboard.js (frontend) to render boards from FEN
      - sets pieceTheme to a CDN path so piece images actually load
      - ALSO renders any FEN strings that appear in explanation text as boards inline.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)

    data_json = json.dumps(data, indent=2)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Chester</title>

  <!-- chessboard.js -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/chessboard-js/1.0.0/chessboard-1.0.0.css"/>

  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      margin: 20px;
      color: #111;
    }}
    .meta {{ color: #555; }}
    .pill {{
      display:inline-block;
      padding:2px 8px;
      border:1px solid #ccc;
      border-radius:999px;
      margin-right:6px;
      font-size:12px;
      background: #fafafa;
    }}
    .card {{
      border: 1px solid #ddd;
      border-radius: 12px;
      padding: 14px;
      margin: 14px 0;
      width: min(1200px, 100%);
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    .row {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: flex-start;
    }}
    .boardWrap {{
      padding: 10px;
      background: #f7f7f8;
      border-radius: 12px;
      border: 1px solid #eee;
    }}
    .board {{ width: 360px; }}
    .boardSmall {{ width: 300px; }}

    .explain {{
      white-space: pre-wrap;
      line-height: 1.35;
      margin-top: 10px;
    }}

    .fenInline {{
      margin: 10px 0;
      padding: 10px;
      border: 1px solid #eee;
      background: #fafafa;
      border-radius: 10px;
    }}
    .fenInline code {{
      display: block;
      margin-bottom: 8px;
      white-space: nowrap;
      overflow-x: auto;
    }}

    details {{ margin-top: 12px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{
      border: 1px solid #e5e5e5;
      padding: 6px;
      vertical-align: top;
      font-size: 14px;
    }}
    code {{
      background: #f1f1f1;
      padding: 2px 6px;
      border-radius: 6px;
    }}
  </style>
</head>

<body>
  <h1 id="title">Chester</h1>

  <div id="init"></div>

  <h2>Overall explanation</h2>
  <div class="card"><div id="overall" class="explain"></div></div>

  <h2>Candidate lines</h2>
  <div id="lines"></div>

  <!-- Inline data: no fetch, no CORS. -->
  <script id="chester-data" type="application/json">
{data_json}
  </script>

  <!-- Dependencies for chessboard.js -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/chessboard-js/1.0.0/chessboard-1.0.0.js"></script>

  <script>
    function getData() {{
      const el = document.getElementById("chester-data");
      return JSON.parse(el.textContent);
    }}

    function orientationFromRequest(data) {{
      const p = (data?.request?.player || "").toLowerCase();
      if (p === "black" || p === "b") return "black";
      return "white";
    }}

    function escapeHtml(s) {{
      return String(s)
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;");
    }}

    function fenToPlacement(fen) {{
      if (!fen) return "8/8/8/8/8/8/8/8";
      return String(fen).split(" ")[0];
    }}

    // IMPORTANT: point chessboard.js to piece images that actually exist (CDN).
    // Otherwise it tries to load local ./img/chesspieces/... and you get broken icons.
    const PIECE_THEME =
      "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/wikipedia/{{piece}}.png";

    function createBoardDiv(className, fen, orientation) {{
      const wrap = document.createElement("div");
      wrap.className = "boardWrap";

      const boardDiv = document.createElement("div");
      boardDiv.className = className;
      wrap.appendChild(boardDiv);

      const placement = fenToPlacement(fen);

      requestAnimationFrame(() => {{
        try {{
          Chessboard(boardDiv, {{
            position: placement,
            orientation: orientation,
            draggable: false,
            pieceTheme: PIECE_THEME
          }});
        }} catch (e) {{
          console.error("Failed to init Chessboard:", e, {{ fen, placement, orientation }});
        }}
      }});

      return wrap;
    }}

    function pillHtml(txt) {{
      const span = document.createElement("span");
      span.className = "pill";
      span.textContent = txt;
      return span.outerHTML;
    }}

    // Detect full FEN strings in text and render them as boards inline.
    // This is intentionally conservative: it looks for 6-field FENs.
    const FEN_RE = /(?:[prnbqkPRNBQK1-8]+\\/){7}[prnbqkPRNBQK1-8]+\\s+[wb]\\s+(?:-|[KQkq]{1,4})\\s+(?:-|[a-h][36])\\s+\\d+\\s+\\d+/g;

    function renderTextWithFen(containerEl, text, orientation) {{
      containerEl.textContent = "";
      const s = String(text || "");
      let last = 0;
      let m;

      while ((m = FEN_RE.exec(s)) !== null) {{
        const start = m.index;
        const end = start + m[0].length;

        if (start > last) {{
          containerEl.appendChild(document.createTextNode(s.slice(last, start)));
        }}

        const fen = m[0];

        const block = document.createElement("div");
        block.className = "fenInline";
        block.innerHTML = `<code>${{escapeHtml(fen)}}</code>`;

        const boardHost = document.createElement("div");
        block.appendChild(boardHost);
        boardHost.appendChild(createBoardDiv("boardSmall", fen, orientation));

        containerEl.appendChild(block);

        last = end;
      }}

      if (last < s.length) {{
        containerEl.appendChild(document.createTextNode(s.slice(last)));
      }}
    }}

    function main() {{
      const data = getData();
      const orient = orientationFromRequest(data);

      document.getElementById("title").textContent = data.title || "Chester";

      const corrected = data?.request?.corrected;
      const correctedTxt = corrected
        ? ` · ⚠ corrected ply: ${{data.request.corrected_from}} → ${{data.request.ply_index}}`
        : "";

      const init = document.getElementById("init");
      init.innerHTML = `
        <div class="card">
          <div class="meta">
            Side to move: <b>${{data.side_to_move}}</b>
            · Requested: ${{data.request.player}} move ${{data.request.move_number}} (ply ${{data.request.ply_index}})
            ${{correctedTxt}}
          </div>
          <div id="init-board-row" class="row" style="margin-top: 10px;"></div>
          <div class="meta" style="margin-top: 10px;">
            FEN: <code>${{escapeHtml(data.initial.fen)}}</code>
          </div>
        </div>
      `;

      // Overall explanation: render FENs as boards inline if present.
      const overallEl = document.getElementById("overall");
      renderTextWithFen(overallEl, data.overall_explanation || "", orient);

      const initRow = document.getElementById("init-board-row");
      initRow.appendChild(createBoardDiv("board", data.initial.fen, orient));

      const linesDiv = document.getElementById("lines");
      (data.lines || []).forEach((line) => {{
        const card = document.createElement("section");
        card.className = "card";

        const pills = (line.labels || []).map(pillHtml).join("");
        const pv = (line.pv_san || []).join(" ");
        const err = line.error
          ? `<div class="meta" style="margin-top:6px;color:#b00;">Error: ${{escapeHtml(line.error)}}</div>`
          : "";

        card.innerHTML = `
          <div>${{pills}}</div>
          <h2 style="margin: 8px 0 6px 0;">
            ${{escapeHtml(line.move_san)}} <span class="meta">(root ${{escapeHtml(line.root_eval_str)}})</span>
          </h2>
          <div class="meta">Line type: <b>${{escapeHtml(line.classification)}}</b></div>
          ${{err}}
          <div class="row" style="margin-top: 10px;">
            <div>
              <div class="meta">Start</div>
              <div class="startBoard"></div>
              <div class="meta" style="margin-top:6px;">FEN: <code>${{escapeHtml(line.start_fen)}}</code></div>
            </div>
            <div>
              <div class="meta">End</div>
              <div class="endBoard"></div>
              <div class="meta" style="margin-top:6px;">FEN: <code>${{escapeHtml(line.end_fen)}}</code></div>
            </div>
          </div>

          <details>
            <summary><b>PV</b> (${{escapeHtml(line.classification)}}) — ${{escapeHtml(pv)}}</summary>
            <div class="meta" style="margin-top:8px;">
              (Boards show the position <i>before</i> each listed move, then the final position.)
            </div>
            <table style="margin-top:8px;">
              <thead><tr><th>#</th><th>Move</th><th>Eval</th><th>Material</th><th>Board</th></tr></thead>
              <tbody class="pvRows"></tbody>
            </table>
          </details>

          <h3>Explanation</h3>
          <div class="explain lineExplain"></div>
        `;

        card.querySelector(".startBoard").appendChild(createBoardDiv("board", line.start_fen, orient));
        card.querySelector(".endBoard").appendChild(createBoardDiv("board", line.end_fen, orient));

        // Line explanation: render FENs as boards inline if present.
        const lineExplainEl = card.querySelector(".lineExplain");
        renderTextWithFen(lineExplainEl, line.explanation || "", orient);

        const tbody = card.querySelector(".pvRows");
        (line.ply || []).forEach((p, idx) => {{
          const tr = document.createElement("tr");
          const mv = p.move_san || "";
          const evalStr = p.eval_str || "";
          const mat = p.material?.values
            ? `W:${{p.material.values.white}} B:${{p.material.values.black}} (Δ ${{p.material.delta}})`
            : "";

          tr.innerHTML = `
            <td>${{idx+1}}</td>
            <td><b>${{escapeHtml(mv)}}</b></td>
            <td>${{escapeHtml(evalStr)}}</td>
            <td>${{escapeHtml(mat)}}</td>
            <td class="pvBoardCell"></td>
          `;

          tr.querySelector(".pvBoardCell").appendChild(createBoardDiv("boardSmall", p.fen, orient));
          tbody.appendChild(tr);
        }});

        linesDiv.appendChild(card);
      }});
    }}

    main();
  </script>
</body>
</html>
"""

    out = dist_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
