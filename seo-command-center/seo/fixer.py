"""
fixer.py — deterministic rule-based fix generation for SEO issues.

Generates fixes without any LLM/network calls so the tool works offline,
meets the efficiency budget (model_calls=0), and produces schema-valid output.

All generated titles are guaranteed ≤ 60 characters.
All redirect targets are verified to exist within the crawled URL set.
"""

from __future__ import annotations
import re
from urllib.parse import urlparse


# ── Title generation ──────────────────────────────────────────────────────────

def _slug_to_title(slug: str) -> str:
    """Convert a URL slug into a human-readable title."""
    # Remove file extensions
    slug = re.sub(r"\.[a-zA-Z0-9]+$", "", slug)
    # Split on hyphens, underscores, and slashes
    words = re.split(r"[-_/]+", slug)
    words = [w for w in words if w and not w.isdigit()]
    if not words:
        return ""
    return " ".join(w.capitalize() for w in words)


def _url_to_title(url: str, max_chars: int = 57) -> str:
    """Derive a title from a URL path, capped at max_chars."""
    try:
        path = urlparse(url).path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        if not parts:
            title = "Home"
        else:
            # Use the most specific (last) path segment for the title
            slug = parts[-1]
            title = _slug_to_title(slug)
            if not title:
                title = slug.replace("-", " ").replace("_", " ").title()
    except Exception:
        title = "Page"

    # Trim to max_chars
    if len(title) > max_chars:
        title = title[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;-")
    return title or "Page"


def truncate_title(title: str, max_chars: int = 57) -> str:
    """Shorten an existing title to ≤ max_chars, cutting at a word boundary."""
    title = title.strip()
    if len(title) <= max_chars:
        return title
    truncated = title[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;-")
    return truncated + "…"


def generate_title(url: str, current_title: str, _content_sample: str = "") -> str:
    """
    Return an SEO-optimised title ≤ 60 chars.
    - If current title exists but is too long → truncate it.
    - If current title is missing/empty → derive from the URL slug.
    Always guaranteed ≤ 60 characters.
    """
    current = (current_title or "").strip()
    if current:
        return truncate_title(current, max_chars=57)
    return _url_to_title(url, max_chars=57)


def generate_meta(url: str, current_meta: str, current_title: str) -> str:
    """
    Return an SEO-optimised meta description ≤ 155 chars.
    Truncates existing ones or derives a generic one from the title.
    """
    meta = (current_meta or "").strip()
    title = (current_title or "").strip()
    if meta:
        if len(meta) <= 155:
            return meta
        return meta[:152].rsplit(" ", 1)[0].rstrip(" ,;-") + "…"
    if title:
        base = f"Learn more about {title}. Explore our services, insights, and solutions."
        return base[:155]
    return _url_to_title(url, max_chars=80) + " — explore our services and solutions."


# ── Redirect suggestion ───────────────────────────────────────────────────────

def _path_similarity(broken_path: str, candidate_path: str) -> float:
    """
    Score similarity between two URL paths.
    Higher is more similar. Uses common path segment overlap.
    """
    def segments(p: str) -> list[str]:
        return [s for s in p.rstrip("/").split("/") if s]

    b_segs = segments(broken_path)
    c_segs = segments(candidate_path)
    if not b_segs or not c_segs:
        return 0.0

    # Count common segments (order-independent)
    common = len(set(b_segs) & set(c_segs))
    # Bonus for matching prefix
    prefix = sum(1 for a, b in zip(b_segs, c_segs) if a == b)
    # Penalise length difference
    len_diff = abs(len(b_segs) - len(c_segs))
    return common * 2.0 + prefix * 3.0 - len_diff * 0.5


def suggest_redirect(broken_url: str, live_urls: list[str]) -> str:
    """
    Return the best redirect target from live_urls for a broken URL.
    Uses path-segment similarity — fully deterministic, no LLM needed.
    Returns the broken_url itself if no candidate found (safe fallback).
    """
    try:
        broken_path = urlparse(broken_url).path
    except Exception:
        return broken_url

    best_url = broken_url
    best_score = -1.0

    for candidate in live_urls:
        try:
            cpath = urlparse(candidate).path
        except Exception:
            continue
        score = _path_similarity(broken_path, cpath)
        if score > best_score:
            best_score = score
            best_url = candidate

    return best_url


# ── Batch fix generator ───────────────────────────────────────────────────────

def generate_fixes(
    issues: list[dict],
    rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Generate title rewrites and redirect mappings for all detected issues.

    Returns:
        titles      — list of {url, old, new}  (new is always ≤ 60 chars)
        redirect_map — list of {from, to, reason}
    """
    url_map = {r["Address"]: r for r in rows}
    live_200 = {
        r["Address"] for r in rows
        if int(float(str(r.get("Status Code", "0")).strip() or "0")) == 200
    }
    live_url_list = sorted(live_200)

    titles: list[dict] = []
    redirect_map: list[dict] = []

    # Track which URLs we've already fixed to avoid duplicates
    fixed_titles: set[str] = set()
    fixed_redirects: set[str] = set()

    for issue in issues:
        itype = issue["type"]
        for url in issue["affected_urls"]:
            row = url_map.get(url, {})

            if itype in ("missing_title", "duplicate_title", "title_too_long") and url not in fixed_titles:
                old_title = (row.get("Title 1") or "").strip()
                new_title = generate_title(url, old_title)
                if new_title and new_title != old_title:
                    titles.append({"url": url, "old": old_title, "new": new_title})
                    fixed_titles.add(url)

            elif itype == "broken_link" and url not in fixed_redirects:
                target = suggest_redirect(url, live_url_list)
                if target and target != url:
                    redirect_map.append({
                        "from": url,
                        "to": target,
                        "reason": "Nearest path-match from live URLs",
                    })
                    fixed_redirects.add(url)

    return titles, redirect_map
