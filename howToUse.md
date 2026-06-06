# 🚀 How to Use SEO Command Center

The SEO Command Center is a professional tool designed to ingest Screaming Frog exports, detect SEO issues using a deterministic rulebook, and provide a live dashboard for monitoring the audit.

## 🛠️ Installation & Setup

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Install Dependencies
The project uses `pandas` for data processing and `mcp` for the server.
```bash
pip install pandas mcp
```

---

## 🚦 Running the Project

There are two ways to run the SEO Command Center: **Headless Mode** (for quick reports) and **Interactive MCP Mode** (for live dashboard and AI integration).

### Option A: Headless Mode (Quick Report)
Use this to generate `report.json` and `report.html` immediately.

```bash
python seo-command-center/run.py sample-export/
```
- **What happens**: It loads the data, runs all 15+ detection rules, generates a summary, and saves the outputs to the `outputs/` folder.
- **Output**: Check `outputs/report.html` for a visual summary of the audit.

### Option B: Interactive MCP Mode (Live Dashboard)
Use this to launch the server and a live monitoring cockpit.

```bash
python seo-command-center/mcp/server.py
```
- **Dashboard**: Once started, open your browser to [http://localhost:7700](http://localhost:7700).
- **Live Updates**: The dashboard will update in real-time as tools are called via the MCP server.

---

## 🤖 Using with Claude Code (AI Integration)

The SEO Command Center is designed as a Claude Code plugin. When connected, Claude can perform the following steps:

1. **Ingest**: `load(export_dir)` — Claude loads the CSV files.
2. **Audit**: `detect_issues()` — Claude triggers the Python-based rulebook.
3. **Prioritize**: `recommend(recommendations)` — Claude analyzes the findings and suggests the most impactful fixes.
4. **Fix**: `set_fixes(titles, redirect_map)` — Claude generates optimized page titles and redirect mappings using its LLM capabilities.
5. **Export**: `write_report()` and `export_report()` — Claude saves the final professional deliverables.

---

## 📋 Detection Rulebook

The tool automatically detects the following issues:

| Issue | Severity | Description |
|---|---|---|
| `missing_title` | High | Indexable pages with no title tag |
| `duplicate_title` | High | Same title on 2+ indexable URLs |
| `broken_link` | High | Status codes in 400-499 |
| `server_error` | High | Status codes in 500-599 |
| `redirect_chain` | High | A redirect that leads to another redirect |
| `orphan_page` | Medium | Indexable 200 pages with 0 inlinks |
| `missing_h1` | Medium | Pages missing an H1 tag |
| `thin_content` | Low | Word count < 200 |
| `slow_page` | Low | Response time > 1.0s |
| ... and more | ... | See `rulebook.md` for the full list |

## 📂 Project Structure
- `seo/detector.py`: The "Brain" — contains all deterministic Python logic.
- `mcp/server.py`: The "Bridge" — exposes tools and hosts the dashboard.
- `dashboard/`: The "Face" — HTML/JS for the live cockpit.
- `outputs/`: The "Deliverables" — where `report.json` and `report.html` are stored.
