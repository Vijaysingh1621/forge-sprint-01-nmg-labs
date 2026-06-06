# SEO Command Center

You are an expert AI engineer building a production-grade Claude Code plugin for Forge Sprint 01.

Goal:
Build a complete SEO Command Center that ingests Screaming Frog exports, detects SEO issues, prioritizes them, generates fixes using a local LLM, serves a live dashboard, and outputs report.json and report.html.

Critical Requirements:

- Must work on unseen exports.
- No hardcoded values.
- No internet dependency.
- Use deterministic code for detection.
- Use LLM only for generating titles, meta descriptions, redirect suggestions, explanations and recommendations.
- Detection must be done using Python logic.

Architecture:

1. Ingest Agent
   - Load CSV files
   - Normalize columns
   - Validate input

2. Audit Agent
   - Detect SEO issues
   - Produce affected URLs

3. Prioritization Agent
   - Assign severity
   - Calculate impact score

4. Fix Agent
   - Generate titles
   - Generate meta descriptions
   - Generate redirect mappings

5. Report Agent
   - Generate report.json
   - Generate report.html

Required Outputs:

outputs/
├── report.json
├── report.html
├── titles_meta_fixes.csv
└── redirect_map.csv

Dashboard Requirements:

- Live URL count
- Current stage
- Issue counters
- Severity breakdown
- Progress bar
- Run duration

Use:
- FastAPI
- Pandas
- Jinja2
- WebSockets

Avoid:
- Hardcoded sample-export assumptions
- Massive prompts to the model
- Sending entire CSV to LLM

Detection Rules:

Missing Title:
Indexable + Status 200 + Empty Title

Duplicate Title:
Same title across multiple indexable URLs

Title Too Long:
Length > 60 OR Pixel Width > 561

Title Too Short:
Length < 30

Missing Meta:
Empty Meta Description

Duplicate Meta:
Same Meta on multiple URLs

Meta Too Long:
Length > 155

Missing H1:
Empty H1

Broken Link:
Status 400-499

Server Error:
Status 500-599

Redirect:
Status 300-399

Redirect Chain:
Redirect -> Redirect

Redirect Loop:
Redirects back to itself

Thin Content:
Word Count < 200

Orphan Page:
Inlinks = 0

Non-indexable Linked:
Non-indexable with Inlinks > 0

Slow Page:
Response Time > 1 second

Always write clean, modular, production-grade code.