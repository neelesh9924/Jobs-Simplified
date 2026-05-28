---
name: project-status
description: Job Apply Engine — full build status, stack, and key architecture decisions (Phases 0–5 complete)
metadata:
  type: project
---

All 5 roadmap phases are built and verified. This is a local, single-user job-application tool.

**Project:** Django project `jobapply` (package at `jobapply/`), single app `core`. Venv at `venv/`.
**Stack (current):** Django 6.0 (upgraded from 4.2 — Python 3.14 incompatibility), SQLite, django-environ, httpx, HTMX 1.9, Alpine.js 3.14, Tailwind CDN, Lucide icons, Inter font.

**Phase status:**
- P0 scaffold, P1 models + RemoteOK adapter + `ingest_jobs`, P2 scoring + region inference + filterable job list, P3 Gemini tailoring + cover letters + diff, P4 kanban Tracker (Application pipeline + stats + FilterPresets), P5 review Queue + follow-ups + Greenhouse adapter.

**Key decisions that diverged from the original roadmap:**
- **LLM provider: Gemini** (`gemini-2.5-flash` via `google-genai` SDK), NOT Claude. Key in `.env` as `GEMINI_API_KEY`. ROADMAP §6 was updated to reflect this. `gemini-1.5-flash` is retired — use 2.5.
- **Resume = LaTeX.** User's real resume is a structured JSON schema (see [[resume-latex-pipeline]]) rendered to `.tex` and compiled to PDF by **tectonic**. There's an on-dashboard LaTeX editor (CodeMirror + live preview).
- **Sources:** RemoteOK (global JSON) + Greenhouse (per-company boards, configured via `GREENHOUSE_BOARDS` in `.env`).

**How to apply:** The roadmap is complete. Further work is "ongoing" Phase 5 territory (more adapters: Lever/Ashby/WWR — each is one new class in `core/sources/`) or polish. Confirm scope before large new features.

**Seed/run:** `python manage.py seed_profile` loads the real resume. `./setup.sh` (or `./start.sh`) runs setup + tmux + cron. `python manage.py ingest_jobs --source remoteok|greenhouse`.
