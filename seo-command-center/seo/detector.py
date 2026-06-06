"""
detector.py — deterministic SEO issue detection from a Screaming Frog internal_all.csv.

Implements every rule from rulebook.md precisely. Detection is pure Python — the model
is used only for judgment (rewriting titles, choosing redirect targets), not for counting.

Rule reference: rulebook.md
"""

from __future__ import annotations
import csv
import os
from collections import defaultdict


def load_rows(export_dir: str) -> list[dict]:
    """Load internal_all.csv from a Screaming Frog export directory."""
    path = os.path.join(export_dir, "internal_all.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ── helpers ──────────────────────────────────────────────────────────────────

def _int(v, default: int = 0) -> int:
    try:
        return int(float(str(v).strip()))
    except Exception:
        return default


def _float(v, default: float = 0.0) -> float:
    try:
        s = str(v).strip()
        return float(s) if s else default
    except Exception:
        return default


def _str(r: dict, key: str) -> str:
    """Return stripped string value, empty string if missing/None."""
    return (r.get(key) or "").strip()


def is_html(r: dict) -> bool:
    return "text/html" in _str(r, "Content Type").lower()


def is_200(r: dict) -> bool:
    return _int(r.get("Status Code")) == 200


def is_indexable(r: dict) -> bool:
    return _str(r, "Indexability").lower() == "indexable"


# ── main detector ─────────────────────────────────────────────────────────────

def detect(rows: list[dict]) -> list[dict]:
    """
    Return a list of issue dicts matching the rulebook exactly:
      {type, severity, affected_urls, count, explanation}

    Pre-filters (per rulebook):
    - Title/meta/H1 checks: only text/html rows.
    - Duplicate checks: only Indexable 200 pages.
    - A page is "indexable" when Indexability == "Indexable".
    """
    issues: list[dict] = []

    def add(issue_type: str, severity: str, urls: list[str], explanation: str) -> None:
        urls = sorted(set(urls))
        if urls:
            issues.append({
                "type": issue_type,
                "severity": severity,
                "affected_urls": urls,
                "count": len(urls),
                "explanation": explanation,
            })

    # Pre-compute filtered subsets
    html_rows = [r for r in rows if is_html(r)]
    html_200  = [r for r in html_rows if is_200(r)]
    idx200    = [r for r in html_200 if is_indexable(r)]  # indexable 200 HTML

    # ── Titles ────────────────────────────────────────────────────────────────

    # missing_title: Title 1 empty, indexable 200 page
    add("missing_title", "High",
        [r["Address"] for r in idx200 if not _str(r, "Title 1")],
        "Indexable pages with no title tag — invisible to search engines.")

    # duplicate_title: same Title 1 on 2+ indexable URLs
    by_title: dict[str, list[str]] = defaultdict(list)
    for r in idx200:
        t = _str(r, "Title 1")
        if t:
            by_title[t].append(r["Address"])
    dup_title_urls = [u for urls in by_title.values() if len(urls) > 1 for u in urls]
    add("duplicate_title", "High", dup_title_urls,
        "Multiple indexable pages share the same title tag, diluting search relevance.")

    # title_too_long: Title 1 Pixel Width > 561 OR Title 1 Length > 60 (indexable 200)
    add("title_too_long", "Medium",
        [r["Address"] for r in idx200
         if _int(r.get("Title 1 Pixel Width")) > 561 or _int(r.get("Title 1 Length")) > 60],
        "Title likely truncated in search results (>60 chars or >561px wide).")

    # title_too_short: Title 1 Length < 30 and not empty (indexable 200)
    add("title_too_short", "Low",
        [r["Address"] for r in idx200
         if 0 < _int(r.get("Title 1 Length")) < 30],
        "Title is too short to be descriptive in search results (<30 chars).")

    # ── Meta Descriptions ─────────────────────────────────────────────────────

    # missing_meta_description: Meta Description 1 empty, indexable 200 page
    add("missing_meta_description", "Medium",
        [r["Address"] for r in idx200 if not _str(r, "Meta Description 1")],
        "Indexable pages with no meta description — search engines will auto-generate one.")

    # duplicate_meta_description: same Meta Description 1 on 2+ indexable URLs
    by_meta: dict[str, list[str]] = defaultdict(list)
    for r in idx200:
        m = _str(r, "Meta Description 1")
        if m:
            by_meta[m].append(r["Address"])
    dup_meta_urls = [u for urls in by_meta.values() if len(urls) > 1 for u in urls]
    add("duplicate_meta_description", "Medium", dup_meta_urls,
        "Multiple pages share the same meta description, reducing click-through diversity.")

    # meta_description_too_long: Meta Description 1 Length > 155 (indexable 200)
    add("meta_description_too_long", "Low",
        [r["Address"] for r in idx200
         if _int(r.get("Meta Description 1 Length")) > 155],
        "Meta description likely truncated in search results (>155 chars).")

    # ── H1 ────────────────────────────────────────────────────────────────────

    # missing_h1: H1-1 empty on a 200 page (all HTML 200, per rulebook)
    add("missing_h1", "Medium",
        [r["Address"] for r in html_200 if not _str(r, "H1-1")],
        "Pages missing an H1 tag — important on-page signal for search engines.")

    # duplicate_h1: same H1-1 on 2+ indexable URLs
    by_h1: dict[str, list[str]] = defaultdict(list)
    for r in idx200:
        h = _str(r, "H1-1")
        if h:
            by_h1[h].append(r["Address"])
    dup_h1_urls = [u for urls in by_h1.values() if len(urls) > 1 for u in urls]
    add("duplicate_h1", "Low", dup_h1_urls,
        "Multiple indexable pages share the same H1 heading.")

    # ── Response Codes ────────────────────────────────────────────────────────

    # broken_link: Status Code in 400–499
    add("broken_link", "High",
        [r["Address"] for r in rows if 400 <= _int(r.get("Status Code")) <= 499],
        "URLs returning a client error (4xx) — must be fixed or redirected.")

    # server_error: Status Code in 500–599
    add("server_error", "High",
        [r["Address"] for r in rows if 500 <= _int(r.get("Status Code")) <= 599],
        "URLs returning a server error (5xx) — indicates backend failures.")

    # redirect: Status Code in 300–399
    add("redirect", "Medium",
        [r["Address"] for r in rows if 300 <= _int(r.get("Status Code")) <= 399],
        "URLs that redirect (3xx) — unnecessary hops waste crawl budget.")

    # redirect_chain: a redirect whose Redirect URL is itself a redirecting URL
    redirect_map: dict[str, str] = {
        r["Address"]: _str(r, "Redirect URL")
        for r in rows if 300 <= _int(r.get("Status Code")) <= 399
    }
    chain_urls = [
        addr for addr, target in redirect_map.items()
        if target and target in redirect_map
    ]
    add("redirect_chain", "High", chain_urls,
        "Redirects that point to another redirect — should be collapsed to a single hop.")

    # ── Content Quality ───────────────────────────────────────────────────────

    # thin_content: Word Count < 200 on an indexable page (idx200)
    add("thin_content", "Low",
        [r["Address"] for r in idx200 if _int(r.get("Word Count")) < 200],
        "Indexable pages with very low word count (<200 words) — may be seen as low-quality.")

    # orphan_page: Inlinks = 0 on an indexable 200 page
    add("orphan_page", "Medium",
        [r["Address"] for r in idx200 if _int(r.get("Inlinks")) == 0],
        "Indexable pages with zero internal inlinks — not reachable via internal navigation.")

    # non_indexable_but_linked: Indexability != Indexable AND Inlinks > 0
    add("non_indexable_but_linked", "Medium",
        [r["Address"] for r in rows
         if not is_indexable(r) and _int(r.get("Inlinks")) > 0],
        "Non-indexable pages still linked internally — wastes crawl budget and confuses users.")

    # slow_page: Response Time > 1.0 (all rows — per rulebook, no content-type filter)
    add("slow_page", "Low",
        [r["Address"] for r in rows if _float(r.get("Response Time")) > 1.0],
        "Resources with response time > 1s — slow assets degrade Core Web Vitals scores.")

    return issues


# ── summarize ─────────────────────────────────────────────────────────────────

def summarize(issues: list[dict]) -> dict:
    """Return summary stats and attach impact_score to each issue."""
    by_sev: dict[str, int] = defaultdict(int)
    weights = {"High": 10, "Medium": 5, "Low": 2}

    for issue in issues:
        by_sev[issue["severity"]] += 1

    return {
        "total_issues": len(issues),
        "by_severity": {
            "High":   by_sev["High"],
            "Medium": by_sev["Medium"],
            "Low":    by_sev["Low"],
        },
    }


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    export_dir = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(export_dir)
    issues = detect(rows)
    summary = summarize(issues)
    print(f"Loaded {len(rows)} rows, detected {len(issues)} issue types.")
    print(json.dumps(summary, indent=2))
    for i in issues:
        print(f"  [{i['severity']:<6}] {i['type']:<30} x{i['count']}")
