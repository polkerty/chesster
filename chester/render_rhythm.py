# chester/render_rhythm.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_rhythm_html(dist_dir: Path, data: Dict[str, Any]) -> Path:
    dist_dir.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(data, indent=2)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{data.get("title","Rhythm")}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>

  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      margin: 18px;
      color: #111;
      background: #fff;
    }}
    h1 {{ margin: 0 0 6px 0; }}
    .meta {{
      color: #555;
      font-size: 13px;
      line-height: 1.4;
      margin-bottom: 14px;
    }}
    .card {{
      border: 1px solid #e6e6e6;
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      background: #fff;
      max-width: 1200px;
    }}
    canvas {{
      width: 100% !important;
      height: 560px !important;
    }}
    details {{
      margin-top: 12px;
    }}
    code {{
      background: #f2f2f2;
      border: 1px solid #e6e6e6;
      padding: 2px 6px;
      border-radius: 8px;
    }}
    .legend {{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
      margin-top:10px;
      color:#555;
      font-size:12px;
    }}
    .pill {{
      display:inline-block;
      border:1px solid #e6e6e6;
      border-radius:999px;
      padding:3px 8px;
      background:#fafafa;
    }}
  </style>
</head>

<body>
  <h1 id="title"></h1>
  <div class="meta" id="meta"></div>

  <div class="card">
    <canvas id="chart"></canvas>
    <div class="legend">
      <span class="pill">Eval filled: white above 0, black below 0</span>
      <span class="pill">Perplexity / Forced: forward-filled (no null gaps)</span>
      <span class="pill">Zero line is dark black</span>
      <span class="pill">Main axis: [-6, 6]</span>
    </div>

    <details>
      <summary><b>Raw JSON</b></summary>
      <pre id="raw" style="white-space:pre-wrap;"></pre>
    </details>
  </div>

  <script id="chester-data" type="application/json">
{data_json}
  </script>

  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

  <script>
    function getData() {{
      return JSON.parse(document.getElementById("chester-data").textContent);
    }}

    function escapeHtml(s) {{
      return String(s || "")
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;");
    }}

    // Forward-fill null/undefined with last seen value.
    // If no prior value, fill with fallback (default 0).
    function ffill(arr, fallback=0) {{
      const out = [];
      let last = fallback;
      for (let i = 0; i < (arr || []).length; i++) {{
        const v = arr[i];
        if (v === null || v === undefined || Number.isNaN(v)) {{
          out.push(last);
        }} else {{
          last = v;
          out.push(v);
        }}
      }}
      return out;
    }}

    // Plugin to draw a thick, black y=0 line on yMain.
    const zeroLinePlugin = {{
      id: "zeroLinePlugin",
      afterDraw(chart) {{
        const yScale = chart.scales?.yMain;
        const xScale = chart.scales?.x;
        if (!yScale || !xScale) return;

        const y = yScale.getPixelForValue(0);
        const left = xScale.left;
        const right = xScale.right;

        const ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.lineWidth = 3;
        ctx.strokeStyle = "black";
        ctx.stroke();
        ctx.restore();
      }}
    }};

    function main() {{
      const data = getData();
      document.getElementById("title").textContent = data.title || "Rhythm";

      const tc = data?.meta?.time_control || {{}};
      const depths = (data?.meta?.depths || []).join(", ");
      const meta = `
        Game: <code>${{escapeHtml(data.lichess_game_id || "")}}</code>
        · Color arg: <b>${{escapeHtml(data.color_arg || "")}}</b>
        · Depths: <code>${{escapeHtml(depths)}}</code> (max <code>${{escapeHtml(String(data?.meta?.depth_max || ""))}}</code>)
        · Width: <code>${{escapeHtml(String(data?.meta?.width || ""))}}</code>
        · PV plies: <code>${{escapeHtml(String(data?.meta?.pv_plies || ""))}}</code>
        · TimeControl: <code>${{escapeHtml(tc.raw || "")}}</code>
      `;
      document.getElementById("meta").innerHTML = meta;
      document.getElementById("raw").textContent = JSON.stringify(data, null, 2);

      const s = data.series || {{}};
      const x = s.ply || [];
      const evals = s.eval_pawns || [];

      // Forward-fill the “every-other-ply” series to avoid Chart.js null-gap weirdness.
      const pw = ffill(s.perplexity_white, 0);
      const pb = ffill(s.perplexity_black_mirrored, 0);
      const fw = ffill(s.forced_dist_white, 0);
      const fb = ffill(s.forced_dist_black_mirrored, 0);

      const tW = s.time_white_sec || [];
      const tB = s.time_black_sec_mirrored || [];

      const ctx = document.getElementById("chart").getContext("2d");

      new Chart(ctx, {{
        type: "line",
        plugins: [zeroLinePlugin],
        data: {{
          labels: x,
          datasets: [
            {{
              label: "Eval (pawns, White+ / Black-)",
              data: evals,
              yAxisID: "yMain",
              tension: 0.2,
              pointRadius: 0,
              borderWidth: 2,
              fill: {{
                target: "origin",
                above: "white",
                below: "black"
              }}
            }},
            {{
              label: "Perplexity (White)",
              data: pw,
              yAxisID: "yMain",
              stepped: true,
              pointRadius: 0,
              borderWidth: 2
            }},
            {{
              label: "Perplexity (Black, mirrored)",
              data: pb,
              yAxisID: "yMain",
              stepped: true,
              pointRadius: 0,
              borderWidth: 2
            }},
            {{
              label: "Moves until forced (White)",
              data: fw,
              yAxisID: "yMain",
              stepped: true,
              pointRadius: 0,
              borderWidth: 2
            }},
            {{
              label: "Moves until forced (Black, mirrored)",
              data: fb,
              yAxisID: "yMain",
              stepped: true,
              pointRadius: 0,
              borderWidth: 2
            }},
            {{
              label: "Time left (White sec)",
              data: tW,
              yAxisID: "yTime",
              tension: 0.0,
              pointRadius: 0,
              borderWidth: 2,
              spanGaps: true
            }},
            {{
              label: "Time left (Black sec, mirrored)",
              data: tB,
              yAxisID: "yTime",
              tension: 0.0,
              pointRadius: 0,
              borderWidth: 2,
              spanGaps: true
            }},
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{
            mode: "index",
            intersect: false
          }},
          plugins: {{
            legend: {{
              position: "top"
            }},
            tooltip: {{
              callbacks: {{
                title: (items) => {{
                  if (!items || !items.length) return "";
                  return `Ply ${{items[0].label}}`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              title: {{ display: true, text: "Ply" }},
              ticks: {{
                color: "black",
                maxTicksLimit: 24
              }},
              grid: {{
                color: "rgba(0,0,0,0.12)"
              }},
              border: {{
                color: "black",
                width: 3
              }}
            }},
            yMain: {{
              position: "left",
              title: {{ display: true, text: "Main (Eval / Perplexity / Forced-distance)" }},
              min: -6,
              max: 6,
              ticks: {{
                color: "black"
              }},
              grid: {{
                color: "rgba(0,0,0,0.12)"
              }},
              border: {{
                color: "black",
                width: 2
              }}
            }},
            yTime: {{
              position: "right",
              title: {{ display: true, text: "Time left (sec) (Black mirrored)" }},
              ticks: {{
                color: "black"
              }},
              grid: {{
                drawOnChartArea: false
              }},
              border: {{
                color: "black",
                width: 2
              }}
            }}
          }}
        }}
      }});
    }}

    main();
  </script>
</body>
</html>
"""
    out = dist_dir / "rhythm.html"
    out.write_text(html, encoding="utf-8")
    return out
