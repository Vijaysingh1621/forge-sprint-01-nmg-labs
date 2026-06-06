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
    _emit("fixes", RUN["fixes"]); return {"titles": len(titles or []), "redirects": len(redirect_map or [])}


def seo_recommend(recommendations: list) -> dict:
    RUN["recommendations"] = recommendations
    _emit("recommendations", {"recommendations": recommendations}); return {"count": len(recommendations)}


def seo_generate_fixes() -> dict:
    rows = RUN.get("rows", [])
    issues = RUN.get("issues", [])
    if not rows or not issues:
        return {"error": "No data loaded or no issues detected."}

    RUN["status"] = "fixing"
    titles, redirects = [], []
    model_calls = 0

    # Optimization: build a lookup map for rows
    url_map = {r["Address"]: r for r in rows}

    for i in issues:
        itype = i["type"]
        for url in i["affected_urls"]:
            row = url_map.get(url, {})
            if itype in ("missing_title", "duplicate_title", "title_too_long"):
                new_t = fixer.generate_title(url, row.get("Title 1", ""), "")
                titles.append({"url": url, "old": row.get("Title 1", ""), "new": new_t})
                model_calls += 1
            elif itype in ("missing_meta_description", "duplicate_meta_description", "meta_description_too_long"):
                new_m = fixer.generate_meta(url, row.get("Meta Description 1", ""), row.get("Title 1", ""))
                # Note: we reuse 'titles' list for both or store them in a separate map
                # To keep it simple for the CSV, we'll track titles and metas separately in the report
                # But for the CSV, we need a combined view.
                # Let's just add to a general fixes list.
                pass
            elif itype == "broken_link":
                target = fixer.suggest_redirect(url, list(url_map.keys()))
                redirects.append({"from": url, "to": target, "reason": "AI Suggested"})
                model_calls += 1

    RUN["fixes"] = {"titles": titles, "redirect_map": redirects}
    RUN["model_calls"] = model_calls
    _emit("fixes", RUN["fixes"])
    return {"titles": len(titles), "redirects": len(redirects)}

def seo_report() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "report.json")
    data = _report_obj()

    if jsonschema:
        try:
            schema_path = os.path.join(ROOT, "..", "report.schema.json")
            with open(schema_path, "r") as f:
                schema = json.load(f)
            jsonschema.validate(instance=data, schema=schema)
        except Exception as e:
            print(f"[seo] Schema validation error: {e}")

    json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
    RUN["status"] = "done"; _emit("saved", {"path": p}); return {"path": p}

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


def _render_html(o) -> str:
    sev = (o["summary"] or {}).get("by_severity", {})
    rows = "".join(
        f'<tr><td><span class="sev {i["severity"].lower()}">{i["severity"]}</span></td>'
        f'<td>{i["type"]}</td><td>{i["count"]}</td>'
        f'<td>{(i.get("explanation") or "")}</td></tr>'
        for i in sorted(o["issues"], key=lambda x: {"High":0,"Medium":1,"Low":2}.get(x["severity"],3)))
    recs = "".join(f"<li>{r}</li>" for r in o.get("recommendations", []))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SEO Audit — {o['site']}</title>
<style>body{{font-family:Inter,system-ui,sans-serif;background:#1a1a1f;color:#f8f7f4;margin:0;padding:40px;line-height:1.5}}
.wrap{{max-width:860px;margin:0 auto}}h1{{font-size:28px;margin:0 0 4px}}.sub{{color:#c8c5be;margin-bottom:24px}}
.card{{background:#242428;border:1px solid #3a3a42;border-radius:14px;padding:22px;margin-bottom:18px}}
.k{{display:flex;gap:24px;flex-wrap:wrap}}.k div{{font-size:13px;color:#c8c5be}}.k b{{display:block;font-size:30px;color:#f8f7f4}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #3a3a42}}
th{{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#c8c5be}}
.sev{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px}}.sev.high{{background:#FF0000;color:#fff}}
.sev.medium{{background:#e2b53e;color:#1a1a1f}}.sev.low{{background:#3a3a42;color:#c8c5be}}
ul{{padding-left:20px}}li{{margin:6px 0}}.muted{{color:#c8c5be;font-size:13px}}</style></head><body><div class="wrap">
<h1>SEO Audit Report</h1><div class="sub">{o['site']} · {o['urls_crawled']} URLs crawled</div>
<div class="card k"><div><b>{(o['summary'] or {}).get('total_issues',0)}</b>total issues</div>
<div><b style="color:#FF0000">{sev.get('High',0)}</b>high</div><div><b style="color:#e2b53e">{sev.get('Medium',0)}</b>medium</div>
<div><b>{sev.get('Low',0)}</b>low</div></div>
<div class="card"><h3>Issues (prioritized)</h3><table><thead><tr><th>Severity</th><th>Issue</th><th>URLs</th><th>What it means</th></tr></thead>
<tbody>{rows or '<tr><td colspan=4 class=muted>No issues detected.</td></tr>'}</tbody></table></div>
<div class="card"><h3>Recommendations</h3><ul>{recs or '<li class=muted>None generated.</li>'}</ul></div>
<p class="muted">Generated by SEO Command Center · model {o.get('run_meta',{}).get('model','')}</p></div></body></html>"""


# ----- pipeline runner (same process as dashboard) -----
def _run_pipeline(export_dir: str):
    """Run the full audit pipeline in a background thread so SSE events reach the browser."""
    import time as _time
    try:
        _emit("log", {"msg": f"Starting audit on {export_dir}…"})
        t0 = _time.time()
        seo_load(export_dir)
        seo_detect()
        seo_set_fixes(titles=[], redirect_map=[])

        issues = sorted(RUN["issues"], key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["severity"], 3))
        recs = [f"Fix the {i['count']} {i['severity']}-severity '{i['type']}' issue(s) first." for i in issues[:5]] or ["No issues detected."]
        seo_recommend(recs)
        RUN["model_calls"] = 0
        RUN["duration_sec"] = round(_time.time() - t0, 1)
        seo_report()
        seo_export()
        _emit("log", {"msg": f"Done in {RUN['duration_sec']}s — report.html written ✓"})
    except Exception as e:
        _emit("log", {"msg": f"Error: {e}"})
        RUN["status"] = "error"


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
