#!/usr/bin/env python3
"""
run.py — headless runner for the SEO Command Center (also the grader's entry point).

Runs the full pipeline on a Screaming Frog export without Claude Code:
  load -> detect -> generate_fixes -> recommend -> write report.json + report.html

Usage:
  python run.py sample-export/
  python run.py sample-export/ --no-dashboard

Fix generation is deterministic (no LLM/network required) — works fully offline.
"""
from __future__ import annotations
import argparse, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mcp"))
sys.path.insert(0, HERE)
import server  # the MCP server module exposes every tool as a function


def main():
    ap = argparse.ArgumentParser(description="SEO Command Center — headless runner")
    ap.add_argument("export_dir", help="Path to a Screaming Frog export directory")
    ap.add_argument("--no-dashboard", action="store_true",
                    help="Skip starting the HTTP dashboard server")
    args = ap.parse_args()

    actual_port = None
    if not args.no_dashboard:
        _, actual_port = server.start_dashboard()
        print(f"[seo] dashboard: http://localhost:{actual_port}", flush=True)
        time.sleep(0.5)

    t0 = time.time()

    # Stage 1 — Load
    print("[seo] Stage 1/4 — Loading CSV…", flush=True)
    load_result = server.seo_load(args.export_dir)
    print(f"[seo] Loaded {load_result['urls']} URLs from {load_result['site']}", flush=True)

    # Stage 2 — Detect
    print("[seo] Stage 2/4 — Running detection rules…", flush=True)
    detect_result = server.seo_detect()
    s = detect_result["summary"]
    print(f"[seo] Detected {s['total_issues']} issue types "
          f"(High:{s['by_severity'].get('High',0)} "
          f"Medium:{s['by_severity'].get('Medium',0)} "
          f"Low:{s['by_severity'].get('Low',0)})", flush=True)

    # Stage 3 — Generate fixes (deterministic, no LLM)
    print("[seo] Stage 3/4 — Generating deterministic fixes…", flush=True)
    fix_result = server.seo_generate_fixes()
    print(f"[seo] Generated {fix_result.get('titles', 0)} title fixes, "
          f"{fix_result.get('redirects', 0)} redirect suggestions", flush=True)

    # Stage 4 — Recommend + Report
    print("[seo] Stage 4/4 — Writing report…", flush=True)
    issues_sorted = sorted(
        server.RUN["issues"],
        key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["severity"], 3)
    )
    recs = [
        f"[{i['severity']}] Fix {i['count']} '{i['type']}' URL(s) — {i.get('explanation', '')}"
        for i in issues_sorted[:8]
    ] or ["No issues detected on this crawl."]
    server.seo_recommend(recs)
    server.RUN["duration_sec"] = round(time.time() - t0, 2)
    server.seo_report()
    server.seo_export()

    # Summary
    s = server.RUN["summary"]
    fx = server.RUN.get("fixes", {})
    print("\n=== SEO AUDIT RESULT ===")
    print(f"Site         : {server.RUN['site']}  ({server.RUN['urls']} URLs)")
    print(f"Total issues : {s['total_issues']}  "
          f"(High {s['by_severity'].get('High',0)} / "
          f"Medium {s['by_severity'].get('Medium',0)} / "
          f"Low {s['by_severity'].get('Low',0)})")
    print(f"Title fixes  : {len(fx.get('titles', []))}")
    print(f"Redirects    : {len(fx.get('redirect_map', []))}")
    print(f"Duration     : {server.RUN['duration_sec']}s")
    print(f"Model calls  : {server.RUN.get('model_calls', 0)}")
    print("Outputs      : outputs/report.json, outputs/report.html, "
          "outputs/titles_meta_fixes.csv, outputs/redirect_map.csv")

    if actual_port:
        print(f"\nDashboard still running at http://localhost:{actual_port}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[seo] Stopped.")


if __name__ == "__main__":
    main()
