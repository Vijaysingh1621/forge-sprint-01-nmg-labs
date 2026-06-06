# Decisions and Learnings Log

## 2026-06-06: Project Setup
- **Decision**: Include `sample-export/` in the repository.
- **Reason**: The folder is small (~1.5MB) and provides essential ground-truth data for users and graders to verify the tool.
- **Result**: Easier onboarding and verification.

## 2026-06-06: Rulebook Implementation
- **Decision**: Implement all 15+ SEO rules in `seo/detector.py` using plain Python logic.
- **Reason**: The rulebook explicitly requires deterministic detection to avoid model instability and quota issues.
- **Result**: Full coverage of the required audit rules (missing titles, redirect chains, slow pages, etc.).

## 2026-06-06: Documentation Strategy
- **Decision**: Create a dedicated `howToUse.md` instead of just a generic README.
- **Reason**: The project has two distinct modes of operation (Headless via `run.py` and Interactive via MCP server), which require clear, separate instructions.
- **Result**: Improved user experience and clarity on how to run the tool.
