"""
server.py — local MCP server + live dashboard host (one process, two faces).

  1. MCP tools over stdio  -> Claude Code calls: seo_load, seo_detect, seo_report, seo_export
  2. HTTP + SSE on localhost:7700 -> the live cockpit that fills as issues are found.

STARTER: works end to end out of the box. Extend the detectors (seo/detector.py) and
the fixes (the model-driven title rewriting / redirect map) during the Sprint.

Needs the MCP SDK to expose tools to Claude (`pip install mcp`); without it the dashboard
still runs so you can use run.py. Standard library otherwise.
"""
from __future__ import annotations
import json, os, queue, threading, time, csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DASH_DIR = os.path.join(ROOT, "dashboard")
OUT_DIR = os.path.join(ROOT, "outputs")
PORT = int(os.environ.get("SEO_PORT", "7700"))
MODEL = os.environ.get("RADAR_MODEL", "gemma4:31b-cloud")

try:
    import jsonschema
except ImportError:
    jsonschema = None

import sys
sys.path.insert(0, ROOT)
from seo import detector, fixer # noqa: E402

RUN = {"site": None, "urls": 0, "issues": [], "summary": None, "status": "idle"}
_subs: list[queue.Queue] = []
_lock = threading.Lock()


def _emit(event, data):
    payload = json.dumps({"event": event, "data": data})
    with _lock:
        for q in list(_subs):
            try: q.put_nowait(payload)
            except Exception: pass


# ----- pipeline tools (importable by run.py without MCP) -----
def seo_load(export_dir: str) -> dict:
    rows = detector.load_rows(export_dir)
    RUN.update({"rows": rows, "urls": len(rows), "issues": [], "summary": None,
                "site": _guess_site(rows), "status": "running"})
    _emit("loaded", {"site": RUN["site"], "urls": len(rows)})
    return {"urls": len(rows), "site": RUN["site"]}


def _guess_site(rows):
    if not rows: return "unknown"
    addr = rows[0].get("Address", "")
    try:
        from urllib.parse import urlparse
        return urlparse(addr).netloc or "unknown"
    except Exception:
        return "unknown"


def seo_detect() -> dict:
    issues = detector.detect(RUN.get("rows", []))
    RUN["issues"] = issues
    RUN["summary"] = detector.summarize(issues)
    for i in issues:
        _emit("issue", i)
    _emit("summary", RUN["summary"])
    return {"detected": len(issues), "summary": RUN["summary"]}


def _report_obj() -> dict:
    return {
        "site": RUN["site"],
        "urls_crawled": RUN["urls"],
        "summary": RUN["summary"] or {"total_issues": 0, "by_severity": {}},
        "issues": RUN["issues"],
        "fixes": RUN.get("fixes", {"titles": [], "redirect_map": []}),
        "recommendations": RUN.get("recommendations", []),
        "run_meta": {"model": MODEL, "model_calls": RUN.get("model_calls", 0),
                     "duration_sec": RUN.get("duration_sec", 0)},
    }


def seo_set_fixes(titles=None, redirect_map=None) -> dict:
    RUN["fixes"] = {"titles": titles or [], "redirect_map": redirect_map or []}
    _emit("fixes", RUN["fixes"])
    return {"titles": len(titles or []), "redirects": len(redirect_map or [])}


def seo_recommend(recommendations: list) -> dict:
    RUN["recommendations"] = recommendations
    _emit("recommendations", {"recommendations": recommendations})
    return {"count": len(recommendations)}


def seo_generate_fixes() -> dict:
    """Generate deterministic title rewrites and redirect suggestions.
    No LLM calls — fully offline, instant, schema-valid output."""
    rows = RUN.get("rows", [])
    issues = RUN.get("issues", [])
    if not rows or not issues:
        return {"error": "No data loaded or no issues detected."}

    RUN["status"] = "fixing"
    _emit("stage", {"stage": "fixing", "msg": "Generating fix suggestions…"})

    titles, redirects = fixer.generate_fixes(issues, rows)

    RUN["fixes"] = {"titles": titles, "redirect_map": redirects}
    RUN["model_calls"] = 0  # deterministic — no model calls
    _emit("fixes", RUN["fixes"])
    return {"titles": len(titles), "redirects": len(redirects)}

def seo_report() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "report.json")
    data = _report_obj()

    if jsonschema:
        # Search for schema in multiple locations (works for any CWD)
        schema_candidates = [
            os.path.join(ROOT, "..", "report.schema.json"),
            os.path.join(ROOT, "report.schema.json"),
            os.path.join(os.getcwd(), "report.schema.json"),
        ]
        schema_path = next((p for p in schema_candidates if os.path.exists(p)), None)
        if schema_path:
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                jsonschema.validate(instance=data, schema=schema)
                print("[seo] report.json schema validation: PASSED ✓", flush=True)
            except jsonschema.ValidationError as e:
                print(f"[seo] Schema validation FAILED: {e.message}", flush=True)
            except Exception as e:
                print(f"[seo] Schema validation error: {e}", flush=True)
        else:
            print("[seo] Schema file not found — skipping validation", flush=True)

    json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
    RUN["status"] = "done"
    _emit("saved", {"path": p})
    return {"path": p}

def seo_export() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. HTML Report
    p_html = os.path.join(OUT_DIR, "report.html")
    open(p_html, "w", encoding="utf-8").write(_render_html(_report_obj()))

    # 2. Titles/Meta CSV
    p_csv = os.path.join(OUT_DIR, "titles_meta_fixes.csv")
    fixes = RUN.get("fixes", {}).get("titles", [])
    with open(p_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "old", "new"])
        writer.writeheader()
        writer.writerows(fixes)

    # 3. Redirect Map CSV
    p_red = os.path.join(OUT_DIR, "redirect_map.csv")
    reds = RUN.get("fixes", {}).get("redirect_map", [])
    with open(p_red, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["from", "to", "reason"])
        writer.writeheader()
        writer.writerows(reds)

    _emit("exported", {"path": p_html}); return {"path": p_html}


def _render_html(o) -> str:  # noqa: C901
    """Render a client-ready HTML report with issues, fixes, and redirect map."""
    sev = (o["summary"] or {}).get("by_severity", {})
    total = (o["summary"] or {}).get("total_issues", 0)
    meta = o.get("run_meta", {})
    fixes_titles = (o.get("fixes") or {}).get("titles", [])
    fixes_redirects = (o.get("fixes") or {}).get("redirect_map", [])

    issue_rows = "".join(
        f'<tr>'
        f'<td><span class="sev {i["severity"].lower()}">{i["severity"]}</span></td>'
        f'<td><code>{i["type"]}</code></td>'
        f'<td style="text-align:right;font-weight:600">{i["count"]}</td>'
        f'<td style="color:#c8c5be">{(i.get("explanation") or "")}</td>'
        f'</tr>'
        for i in sorted(o["issues"], key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["severity"], 3))
    )

    recs_html = "".join(
        f'<li>{r}</li>' for r in o.get("recommendations", [])
    ) or '<li class="muted">No recommendations generated.</li>'

    title_rows = "".join(
        f'<tr><td style="word-break:break-all;font-size:11px;color:#9ca3af">{fix["url"]}</td>'
        f'<td style="color:#f87171;font-size:12px">{fix.get("old") or "<em>empty</em>"}</td>'
        f'<td style="color:#4ade80;font-size:12px;font-weight:600">{fix["new"]}</td></tr>'
        for fix in fixes_titles[:50]  # cap at 50 for readability
    ) or '<tr><td colspan="3" class="muted">No title fixes generated.</td></tr>'

    redirect_rows = "".join(
        f'<tr><td style="word-break:break-all;font-size:11px;color:#f87171">{r["from"]}</td>'
        f'<td style="word-break:break-all;font-size:11px;color:#4ade80">{r["to"]}</td>'
        f'<td style="font-size:11px;color:#9ca3af">{r.get("reason","")}</td></tr>'
        for r in fixes_redirects[:30]
    ) or '<tr><td colspan="3" class="muted">No redirects generated.</td></tr>'

    duration = meta.get("duration_sec", 0)
    model_calls = meta.get("model_calls", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="SEO audit report for {o['site']} — {total} issues detected across {o['urls_crawled']} URLs.">
  <title>SEO Audit Report — {o['site']}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:Inter,system-ui,sans-serif;background:#0f0f13;color:#f8f7f4;line-height:1.6;padding:0 0 60px}}
    .topbar{{background:linear-gradient(135deg,#1a1a2e,#16213e);border-bottom:1px solid #2d2d3a;padding:20px 40px;display:flex;align-items:center;gap:16px}}
    .topbar h1{{font-size:20px;font-weight:700;letter-spacing:-.3px}}
    .dot{{width:10px;height:10px;border-radius:50%;background:#ef4444;display:inline-block;margin-right:8px}}
    .wrap{{max-width:940px;margin:0 auto;padding:32px 24px}}
    .kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:24px}}
    .kpi-card{{background:#1c1c24;border:1px solid #2d2d3a;border-radius:14px;padding:18px 20px}}
    .kpi-card .val{{font-size:36px;font-weight:700;line-height:1}}
    .kpi-card .lbl{{font-size:12px;color:#9ca3af;margin-top:4px}}
    .high-val{{color:#ef4444}}.medium-val{{color:#f59e0b}}.low-val{{color:#6b7280}}.ok-val{{color:#4ade80}}
    .meta-row{{display:flex;gap:20px;flex-wrap:wrap;font-size:12.5px;color:#6b7280;margin-bottom:24px}}
    .meta-row span{{background:#1c1c24;border:1px solid #2d2d3a;border-radius:6px;padding:4px 10px}}
    .card{{background:#1c1c24;border:1px solid #2d2d3a;border-radius:14px;padding:22px;margin-bottom:18px}}
    .card h2{{font-size:13px;text-transform:uppercase;letter-spacing:.12em;color:#6b7280;margin-bottom:16px;font-weight:600}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}
    th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #2d2d3a;vertical-align:top}}
    th{{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:#6b7280;font-weight:600}}
    .sev{{font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}}
    .sev.high{{background:#ef4444;color:#fff}}
    .sev.medium{{background:#f59e0b;color:#000}}
    .sev.low{{background:#374151;color:#9ca3af}}
    code{{font-family:monospace;font-size:12px;color:#a78bfa;background:#1e1b4b;padding:1px 5px;border-radius:4px}}
    ul{{padding-left:18px}}li{{margin:7px 0;font-size:13.5px}}
    .muted{{color:#6b7280;font-size:12.5px}}
    .footer{{text-align:center;color:#4b5563;font-size:12px;margin-top:36px}}
  </style>
</head>
<body>
<div class="topbar">
  <span class="dot"></span>
  <h1>SEO Audit Report</h1>
  <span style="margin-left:auto;font-size:13px;color:#9ca3af">{o['site']} &nbsp;·&nbsp; {o['urls_crawled']} URLs crawled</span>
</div>
<div class="wrap">

  <div class="kpi">
    <div class="kpi-card"><div class="val">{total}</div><div class="lbl">Total issue types</div></div>
    <div class="kpi-card"><div class="val high-val">{sev.get('High',0)}</div><div class="lbl">High severity</div></div>
    <div class="kpi-card"><div class="val medium-val">{sev.get('Medium',0)}</div><div class="lbl">Medium severity</div></div>
    <div class="kpi-card"><div class="val low-val">{sev.get('Low',0)}</div><div class="lbl">Low severity</div></div>
    <div class="kpi-card"><div class="val ok-val">{len(fixes_titles)}</div><div class="lbl">Title fixes</div></div>
    <div class="kpi-card"><div class="val ok-val">{len(fixes_redirects)}</div><div class="lbl">Redirects mapped</div></div>
  </div>

  <div class="meta-row">
    <span>⏱ {duration}s audit time</span>
    <span>🤖 {model_calls} model calls</span>
    <span>🔧 Deterministic detection</span>
  </div>

  <div class="card">
    <h2>Issues Found (prioritized by severity)</h2>
    <table><thead><tr><th>Severity</th><th>Issue type</th><th style="text-align:right">URLs</th><th>What it means</th></tr></thead>
    <tbody>{issue_rows or '<tr><td colspan="4" class="muted">No issues detected.</td></tr>'}</tbody></table>
  </div>

  <div class="card">
    <h2>Recommendations</h2>
    <ul>{recs_html}</ul>
  </div>

  <div class="card">
    <h2>Title Fixes ({len(fixes_titles)} rewrites)</h2>
    <table><thead><tr><th>URL</th><th>Current title</th><th>Suggested title</th></tr></thead>
    <tbody>{title_rows}</tbody></table>
    {f'<p class="muted" style="margin-top:10px">Showing first 50 of {len(fixes_titles)}.</p>' if len(fixes_titles) > 50 else ''}
  </div>

  <div class="card">
    <h2>Redirect Map ({len(fixes_redirects)} suggestions)</h2>
    <table><thead><tr><th>Broken URL</th><th>Suggested target</th><th>Reason</th></tr></thead>
    <tbody>{redirect_rows}</tbody></table>
  </div>

  <div class="footer">Generated by SEO Command Center &nbsp;·&nbsp; model: {meta.get('model','deterministic')}</div>
</div>
</body></html>"""


# ----- pipeline runner (same process as dashboard) -----
def _run_pipeline(export_dir: str):
    """Run the full audit pipeline in a background thread so SSE events reach the browser."""
    import time as _time
    try:
        t0 = _time.time()

        # Stage 1: Load
        _emit("stage", {"stage": "loading", "msg": f"Loading CSV from {export_dir}…"})
        _emit("log", {"msg": f"Stage 1/4 — Loading export from {export_dir}"})
        seo_load(export_dir)
        _emit("log", {"msg": f"Loaded {RUN['urls']} URLs from {RUN['site']}"})

        # Stage 2: Detect
        _emit("stage", {"stage": "detecting", "msg": "Running SEO rulebook detectors…"})
        _emit("log", {"msg": "Stage 2/4 — Running 17 detection rules"})
        seo_detect()
        s = RUN["summary"]
        _emit("log", {"msg": f"Detected {s['total_issues']} issue types (High:{s['by_severity'].get('High',0)} Medium:{s['by_severity'].get('Medium',0)} Low:{s['by_severity'].get('Low',0)})"})

        # Stage 3: Generate fixes (deterministic)
        _emit("stage", {"stage": "fixing", "msg": "Generating deterministic fixes…"})
        _emit("log", {"msg": "Stage 3/4 — Generating title rewrites & redirect suggestions"})
        seo_generate_fixes()
        fx = RUN.get("fixes", {})
        _emit("log", {"msg": f"Generated {len(fx.get('titles',[]))} title fixes, {len(fx.get('redirect_map',[]))} redirect suggestions"})

        # Stage 4: Recommend + Report
        _emit("stage", {"stage": "reporting", "msg": "Building recommendations & writing report…"})
        _emit("log", {"msg": "Stage 4/4 — Writing report.json and report.html"})
        issues_sorted = sorted(RUN["issues"], key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["severity"], 3))
        recs = [
            f"[{i['severity']}] Fix {i['count']} '{i['type']}' URL(s) — {i.get('explanation','')}"
            for i in issues_sorted[:8]
        ] or ["No issues detected on this crawl."]
        seo_recommend(recs)
        RUN["duration_sec"] = round(_time.time() - t0, 2)
        seo_report()
        seo_export()

        _emit("log", {"msg": f"✓ Done in {RUN['duration_sec']}s — report.html ready"})
        _emit("stage", {"stage": "done", "msg": f"Completed in {RUN['duration_sec']}s"})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _emit("log", {"msg": f"Error: {e}"})
        _emit("stage", {"stage": "error", "msg": str(e)})
        RUN["status"] = "error"
        print(f"[seo] Pipeline error: {tb}", flush=True)


# ----- dashboard HTTP host -----
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            export_dir = data.get("export_dir", os.path.join(ROOT, "..", "sample-export"))
            export_dir = os.path.abspath(export_dir)
            if RUN.get("status") == "running":
                self._send(409, json.dumps({"error": "audit already running"}), "application/json")
                return
            threading.Thread(target=_run_pipeline, args=(export_dir,), daemon=True).start()
            self._send(200, json.dumps({"started": True, "export_dir": export_dir}), "application/json")
        else:
            self._send(404, "not found")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            p = os.path.join(DASH_DIR, "index.html")
            self._send(200, open(p, encoding="utf-8").read() if os.path.exists(p) else "no dashboard")
        elif self.path == "/app.js":
            p = os.path.join(DASH_DIR, "app.js")
            self._send(200, open(p, encoding="utf-8").read() if os.path.exists(p) else "", "application/javascript")
        elif self.path == "/state":
            self._send(200, json.dumps({k: v for k, v in RUN.items() if k != "rows"}), "application/json")
        elif self.path == "/events":
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q = queue.Queue()
            with _lock: _subs.append(q)
            try:
                snap = {k: v for k, v in RUN.items() if k != "rows"}
                self.wfile.write(f"data: {json.dumps({'event':'snapshot','data':snap})}\n\n".encode()); self.wfile.flush()
                while True:
                    try: self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                    except queue.Empty: self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception: pass
            finally:
                with _lock:
                    if q in _subs: _subs.remove(q)
        else: self._send(404, "not found")


def start_dashboard(port=PORT):
    import socket
    # Try the requested port, then increment until a free one is found
    for attempt in range(20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port + attempt), H)
            httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            actual_port = port + attempt
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            if actual_port != PORT:
                print(f"[seo] Port {PORT} busy — using port {actual_port} instead", flush=True)
            return httpd, actual_port
        except OSError:
            continue
    raise OSError(f"Could not find a free port starting from {port}")


def _run_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print(f"[seo] MCP SDK not found. Dashboard only at http://localhost:{PORT}", flush=True)
        while True: time.sleep(3600)
    mcp = FastMCP("seo-command-center")

    @mcp.tool()
    def load(export_dir: str) -> dict:
        """Load a Screaming Frog export directory (expects internal_all.csv)."""
        return seo_load(export_dir)

    @mcp.tool()
    def detect_issues() -> dict:
        """Run the SEO rulebook detectors over the loaded crawl."""
        return seo_detect()

    @mcp.tool()
    def set_fixes(titles: list = None, redirect_map: list = None) -> dict:
        """Attach the model-written title rewrites and the redirect map."""
        return seo_set_fixes(titles, redirect_map)

    @mcp.tool()
    def recommend(recommendations: list) -> dict:
        """Attach the prioritized recommendations."""
        return seo_recommend(recommendations)

    @mcp.tool()
    def write_report() -> dict:
        """Write outputs/report.json."""
        return seo_report()

    @mcp.tool()
    def export_report() -> dict:
        """Write outputs/report.html (the client deliverable)."""
        return seo_export()

    mcp.run()


if __name__ == "__main__":
    _, actual_port = start_dashboard()
    print(f"[seo] dashboard live at http://localhost:{actual_port}", flush=True)
    _run_mcp()
