# chester/render_web_v2.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_web_v2(dist_dir: Path, data: Dict[str, Any]) -> Path:
    dist_dir.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(data, indent=2)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Chester</title>

  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/chessboard-js/1.0.0/chessboard-1.0.0.css"/>

  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      margin: 18px;
      color: #111;
      background: #fff;
    }}
    h1 {{ margin: 0 0 12px 0; }}
    h2 {{ margin: 18px 0 10px 0; }}

    .card {{
      border: 1px solid #e6e6e6;
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      background: #fff;
    }}

    .meta {{
      color: #555;
      font-size: 13px;
      margin-top: 6px;
      line-height: 1.35;
    }}

    .label {{
      font-size: 13px;
      color: #333;
      font-weight: 700;
      letter-spacing: 0.2px;
      margin-bottom: 8px;
    }}

    .pill {{
      display:inline-block;
      padding: 2px 8px;
      border: 1px solid #ddd;
      border-radius: 999px;
      margin-right: 6px;
      font-size: 12px;
      background: #fafafa;
      color: #333;
    }}

    .row {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      align-items: flex-start;
    }}

    .boardWrap {{
      padding: 10px;
      background: #f7f7f8;
      border-radius: 12px;
      border: 1px solid #eee;
      flex: 0 0 auto;
    }}
    .board {{ width: 340px; }}
    .boardSmall {{ width: 280px; }}

    .text {{
      white-space: pre-wrap;
      line-height: 1.35;
      font-size: 14px;
    }}

    .columns {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 14px;
      align-items: start;
    }}

    details.col {{
      border: 1px solid #e6e6e6;
      border-radius: 14px;
      background: #fff;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      overflow: hidden;
    }}
    details.col > summary {{
      cursor: pointer;
      list-style: none;
      padding: 12px 14px;
      user-select: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    details.col > summary::-webkit-details-marker {{
      display:none;
    }}
    .colSummaryLeft {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }}
    .colTitle {{
      font-size: 16px;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .colSub {{
      color: #666;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .colBody {{
      padding: 14px;
      border-top: 1px solid #eee;
    }}

    .posCard {{
      border: 1px solid #eee;
      border-radius: 12px;
      padding: 12px;
      background: #fff;
      margin-bottom: 12px;
    }}

    .posHeader {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 8px;
    }}
    .posHeader .posLabel {{
      font-weight: 800;
      font-size: 13px;
      color: #333;
    }}
    .posHeader .posEval {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
      color: #333;
      background: #f2f2f2;
      border-radius: 10px;
      padding: 2px 8px;
      border: 1px solid #e6e6e6;
      white-space: nowrap;
    }}

    .kv {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 8px 0 8px 0;
      color: #555;
      font-size: 12px;
    }}
    .kv span {{
      background: #fafafa;
      border: 1px solid #eee;
      padding: 2px 8px;
      border-radius: 999px;
    }}

    .sectionDetails {{
      margin-top: 10px;
    }}
    .sectionDetails summary {{
      cursor: pointer;
      font-weight: 800;
      color: #333;
    }}

    code {{
      background: #f2f2f2;
      border: 1px solid #e6e6e6;
      padding: 2px 6px;
      border-radius: 8px;
    }}
  </style>
</head>

<body>
  <h1 id="title">Chester</h1>

  <div id="starting"></div>

  <h2>Candidate moves</h2>
  <div id="cols" class="columns"></div>

  <script id="chester-data" type="application/json">
{data_json}
  </script>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/chessboard-js/1.0.0/chessboard-1.0.0.js"></script>

  <script>
    const PIECE_THEME =
      "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/wikipedia/{{piece}}.png";

    function getData() {{
      return JSON.parse(document.getElementById("chester-data").textContent);
    }}

    function escapeHtml(s) {{
      return String(s || "")
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;");
    }}

    function fenToPlacement(fen) {{
      if (!fen) return "8/8/8/8/8/8/8/8";
      return String(fen).split(" ")[0];
    }}

    function createBoard(className, fen, orientation) {{
      const wrap = document.createElement("div");
      wrap.className = "boardWrap";
      const div = document.createElement("div");
      div.className = className;
      wrap.appendChild(div);

      const placement = fenToPlacement(fen);

      requestAnimationFrame(() => {{
        Chessboard(div, {{
          position: placement,
          orientation: orientation,
          draggable: false,
          pieceTheme: PIECE_THEME
        }});
      }});

      return wrap;
    }}

    function pills(labels) {{
      return (labels || []).map(l => `<span class="pill">${{escapeHtml(l)}}</span>`).join("");
    }}

    function posCard(node, orientation, boardClass) {{
      const card = document.createElement("div");
      card.className = "posCard";

      card.innerHTML = `
        <div class="posHeader">
          <div class="posLabel">${{escapeHtml(node.label || "")}}</div>
          <div class="posEval">${{escapeHtml(node.eval_str || "")}}</div>
        </div>
        <div class="kv">
          <span>To move: <b>${{escapeHtml(node.side_to_move || "")}}</b></span>
          <span>Move: <b>${{escapeHtml(node.move_san || "")}}</b></span>
        </div>
        <div class="row">
          <div class="boardHost"></div>
          <div style="flex: 1 1 220px; min-width: 220px;">
            <div class="text">${{escapeHtml(node.summary || "")}}</div>
            <div class="meta" style="margin-top:8px;">FEN: <code>${{escapeHtml(node.fen || "")}}</code></div>
          </div>
        </div>
      `;

      card.querySelector(".boardHost").appendChild(createBoard(boardClass, node.fen, orientation));
      return card;
    }}

    function startingCard(starting, orientation) {{
      const wrap = document.createElement("div");
      wrap.className = "card";

      const ep = starting.engine_preferred || {{}};

      wrap.innerHTML = `
        <div class="label">Starting position</div>
        <div class="row">
          <div class="boardHost"></div>
          <div style="flex: 1 1 260px; min-width: 260px;">
            <div class="kv">
              <span>To move: <b>${{escapeHtml(starting.side_to_move || "")}}</b></span>
              <span>Eval: <b>${{escapeHtml(starting.eval_str || "")}}</b></span>
            </div>
            <div class="text">${{escapeHtml(starting.summary || "")}}</div>

            <details class="sectionDetails" open>
              <summary>Engine preferred move</summary>
              <div class="meta" style="margin-top:8px;">
                Move: <b>${{escapeHtml(ep.move_san || "")}}</b> (<code>${{escapeHtml(ep.move_uci || "")}}</code>)
              </div>
              <div class="text" style="margin-top:6px;">${{escapeHtml(ep.reason || "")}}</div>
            </details>

            <div class="meta" style="margin-top:10px;">FEN: <code>${{escapeHtml(starting.fen || "")}}</code></div>
          </div>
        </div>
      `;

      wrap.querySelector(".boardHost").appendChild(createBoard("board", starting.fen, orientation));
      return wrap;
    }}

    function buildColumn(line, orientation) {{
      const det = document.createElement("details");
      det.className = "col";
      det.open = true;

      const title = `${{line.move_san}}`;
      const sub = `root ${{line.root_eval_str}} · ${{(line.pv_san || []).slice(0, 10).join(" ")}}`;

      det.innerHTML = `
        <summary>
          <div class="colSummaryLeft">
            <div>${{pills(line.labels)}}</div>
            <div class="colTitle">${{escapeHtml(title)}}</div>
            <div class="colSub">${{escapeHtml(sub)}}</div>
          </div>
          <div style="color:#666;font-size:12px;white-space:nowrap;">(collapse)</div>
        </summary>
        <div class="colBody"></div>
      `;

      const body = det.querySelector(".colBody");

      // First node is the candidate move position (idx=1)
      const nodes = line.nodes || [];
      if (nodes.length > 0) {{
        body.appendChild(posCard(nodes[0], orientation, "board"));
      }}

      // PV stack (remaining nodes)
      if (nodes.length > 1) {{
        const pvDetails = document.createElement("details");
        pvDetails.className = "sectionDetails";
        pvDetails.open = true;
        pvDetails.innerHTML = `<summary>Principal variation positions</summary>`;
        const pvWrap = document.createElement("div");
        pvWrap.style.marginTop = "10px";

        nodes.slice(1).forEach((n) => {{
          pvWrap.appendChild(posCard(n, orientation, "boardSmall"));
        }});

        pvDetails.appendChild(pvWrap);
        body.appendChild(pvDetails);
      }}

      // End sections
      const overall = document.createElement("details");
      overall.className = "sectionDetails";
      overall.open = true;
      overall.innerHTML = `
        <summary>Overall analysis of the line</summary>
        <div class="text" style="margin-top:10px;">${{escapeHtml(line.line_overall || "")}}</div>
      `;
      body.appendChild(overall);

      const comp = document.createElement("details");
      comp.className = "sectionDetails";
      comp.open = false;
      comp.innerHTML = `
        <summary>Comparison vs other lines</summary>
        <div class="text" style="margin-top:10px;">${{escapeHtml(line.line_compare || "")}}</div>
      `;
      body.appendChild(comp);

      return det;
    }}

    function orientationFromRequest() {{
      // Keep consistent view (white-bottom) by default.
      // If you want "player perspective", wire this to your CLI request.player.
      return "white";
    }}

    function main() {{
      const data = getData();
      const orient = orientationFromRequest();

      document.getElementById("title").textContent = data.title || "Chester";

      const startingDiv = document.getElementById("starting");
      startingDiv.appendChild(startingCard(data.starting || {{}}, orient));

      const cols = document.getElementById("cols");
      (data.lines || []).forEach((line) => {{
        cols.appendChild(buildColumn(line, orient));
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
