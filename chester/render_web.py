from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Chester</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 20px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 14px; margin: 14px 0; width: min(1100px, 100%); }
    .meta { color: #555; }
    .pill { display:inline-block; padding:2px 8px; border:1px solid #ccc; border-radius:999px; margin-right:6px; font-size:12px; }
    .boards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .svgwrap { background:#f7f7f8; border-radius:10px; padding:10px; overflow:auto; }
    pre { background:#f7f7f8; padding:10px; border-radius:10px; overflow:auto; }
    details { margin-top: 10px; }
    .explain { white-space: pre-wrap; line-height: 1.35; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border: 1px solid #e5e5e5; padding: 6px; vertical-align: top; }
  </style>
</head>
<body>
  <h1 id="title">Chester</h1>
  <div id="init"></div>
  <h2>Overall explanation</h2>
  <div class="card"><div id="overall" class="explain"></div></div>
  <h2>Candidate lines</h2>
  <div id="lines"></div>

<script>
async function main(){
  const res = await fetch("./data.json");
  const data = await res.json();

  document.getElementById("title").textContent = data.title;

  document.getElementById("init").innerHTML = `
    <div class="card">
      <div class="meta">
        Side to move: <b>${data.side_to_move}</b> · Requested: ${data.request.player} move ${data.request.move_number} (ply ${data.request.ply_index})
        ${data.request.corrected ? " · ⚠ corrected ply: " + data.request.corrected_from + " → " + data.request.ply_index : ""}
      </div>
      <div class="row">
        <div class="svgwrap">${data.initial.svg}</div>
      </div>
    </div>
  `;

  document.getElementById("overall").textContent = data.overall_explanation || "";

  const linesDiv = document.getElementById("lines");
  for (const line of data.lines) {
    const pills = line.labels.map(x => `<span class="pill">${x}</span>`).join("");
    const pv = line.pv_san.join(" ");
    const rows = line.ply.map((p,i) => `
      <tr>
        <td>${i+1}</td>
        <td><b>${p.move_san || ""}</b></td>
        <td>${p.eval_str}</td>
        <td>W:${p.material.values.white} B:${p.material.values.black} (Δ ${p.material.delta})</td>
      </tr>
      <tr>
        <td colspan="4"><div class="svgwrap">${p.svg}</div></td>
      </tr>
    `).join("");

    linesDiv.innerHTML += `
      <section class="card">
        <div>${pills}</div>
        <h2>${line.move_san} <span class="meta">(root ${line.root_eval_str})</span></h2>
        <div class="boards">
          <div>
            <div class="meta">Start</div>
            <div class="svgwrap">${line.start_svg}</div>
          </div>
          <div>
            <div class="meta">End</div>
            <div class="svgwrap">${line.end_svg}</div>
          </div>
        </div>

        <details>
          <summary><b>PV</b> (${line.classification}) — ${pv}</summary>
          <table>
            <thead><tr><th>#</th><th>Move</th><th>Eval</th><th>Material</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </details>

        <h3>Explanation</h3>
        <div class="explain">${(line.explanation||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")}</div>
      </section>
    `;
  }
}
main();
</script>
</body>
</html>
"""

def write_web(dist_dir: Path, data: Dict[str, Any]) -> Path:
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist_dir / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dist_dir / "index.html"
