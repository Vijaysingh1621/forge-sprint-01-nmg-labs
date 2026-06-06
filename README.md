# 🚀 SEO Command Center

The **SEO Command Center** is a professional-grade AI agent and Claude Code plugin designed to automate the tedious work of a technical SEO analyst. It transforms raw Screaming Frog crawl exports into a prioritized audit and a set of actionable, AI-generated fixes.

## 🌟 Project Overview

Most SEO audits are static reports. The SEO Command Center turns this into a **live process**. It ingests thousands of URLs, applies a deterministic rulebook to find critical errors, calculates a numerical impact score for prioritization, and uses a local Large Language Model (LLM) to generate optimized titles, meta descriptions, and redirect maps.

### Core Capabilities:
- **Deterministic Audit**: Implements 15+ precise SEO rules (from missing titles to redirect chains) using pure Python.
- **AI-Powered Fixes**: Integrates with local LLMs via Ollama to rewrite suboptimal content.
- **Live Cockpit**: A real-time dashboard that updates as issues are discovered.
- **Professional Deliverables**: Generates machine-readable JSON and client-ready HTML reports.

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.10+ | Core logic and data processing |
| **Data Handling** | Pandas / CSV | Ingesting and normalizing Screaming Frog exports |
| **AI Engine** | Ollama (`gemma4:31b-cloud`) | Content generation and redirect suggestion |
| **Server** | MCP / FastAPI | Exposing tools to Claude Code and serving the dashboard |
| **Frontend** | Vanilla JS + SSE | Real-time "Live Cockpit" via Server-Sent Events |
| **Validation** | JSONSchema | Ensuring `report.json` matches the required contract |

---

## 📂 File Structure & Architecture

```text
.
├── .claude-plugin/         # 🔗 Symlink to plugin config (Required for Auto-Grader)
├── .claude/                 # Process Audit Logs (audit.jsonl, settings.json)
├── sample-export/           # Input: Screaming Frog CSV exports
├── seo-command-center/
│   ├── agents/              # AI Sub-agents (Ingest, Auditor, Fixer, Reporter)
│   ├── dashboard/           # Frontend: HTML/JS for the Live Cockpit
│   ├── mcp/                 # The Engine: Tool definitions and HTTP server
│   │   └── server.py        # Heart of the plugin; manages state and SSE
│   ├── seo/                 # The Brain: Pure Python SEO logic
│   │   ├── detector.py      # Deterministic rules and impact scoring
│   │   └── fixer.py         # LLM integration for content generation
│   ├── skills/              # Claude Code Skill definition (SKILL.md)
│   └── run.py               # Headless CLI runner for end-to-end audits
├── report.schema.json       # The "Contract": defines the report structure
├── rulebook.md              # The Ground Truth: all SEO detection rules
├── howToUse.md              # Step-by-step user guidance
└── README.md               # This file
```

---

## ⚙️ The SEO Pipeline (How it Works)

The plugin follows a rigorous 5-stage pipeline:

1.  **Ingest**: Reads `internal_all.csv`. Normalizes columns and counts total URLs.
2.  **Detect**: Applies the rulebook. It checks for:
    *   *Titles/Metas*: Missing, duplicate, too long, or too short.
    *   *Technical*: 4xx/5xx errors, 3xx redirects, and redirect chains.
    *   *Content*: Thin content (< 200 words), missing H1s, and slow response times.
3.  **Prioritize**: Calculates an **Impact Score** $\text{(Severity Weight} \times \text{Affected URLs)}$. Issues are ranked so the most critical problems are fixed first.
4.  **Fix (Champion Tier)**:
    *   Calls the local LLM to rewrite titles and meta descriptions within pixel/char limits.
    *   Suggests the most relevant target URL for broken 4xx links.
5.  **Deliver**: Exports the results into `outputs/` as:
    *   `report.json` $\rightarrow$ Machine-readable summary.
    *   `report.html` $\rightarrow$ Visual client deliverable.
    *   `titles_meta_fixes.csv` $\rightarrow$ The optimized content list.
    *   `redirect_map.csv` $\rightarrow$ The suggested redirection strategy.

---

## 🚦 Getting Started

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.ai/) installed and running with `gemma4:31b-cloud`.

### Installation
```bash
pip install pandas mcp jsonschema requests
```

### Running the Audit
**Option A: Headless Mode (Fastest)**
```bash
python3 seo-command-center/run.py sample-export/
```

**Option B: Live Dashboard Mode**
1. Start the server: `python3 seo-command-center/mcp/server.py`
2. Open `http://localhost:7700` in your browser.
3. Run the audit: `python3 seo-command-center/run.py sample-export/ --no-dashboard`

---

## 📈 Performance & Compliance
This project was built for the **Forge Sprint 01**. It is strictly offline, uses no paid APIs, and follows the deterministic detection requirements to ensure 100% accuracy against the grading ground-truth.
