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

**Relevance / scoring (tuned after user feedback that results weren't Android-narrowed):**
- Scoring is **title-driven**: keyword/skill matches in the TITLE weigh ~6x a description match; **tags are down-weighted to ~0.5** because RemoteOK auto-attaches noisy junk tags. See `core/services/scoring.py`.
- `RELEVANCE_THRESHOLD = 0.25`: the job list **hides score < threshold by default**; `?all=1` ("Show all" toggle) shows everything.
- `GREENHOUSE_BOARDS` default = **mobile-heavy boards** (robinhood, reddit, lyft, duolingo, instacart, chime) — gitlab/figma had zero Android roles. Editable in `.env`.
- **Manual job entry** (`/jobs/add/`, `source_key="manual"`): paste a JD you found (LinkedIn/Naukri) → scored, tailorable, auto-added to pipeline as Interested. This is the answer to India/on-site roles not being auto-sourced.
- Sidebar **pinned views**: Remote (`?region=remote`) and India/On-site (`?region=india`) — filter-backed, not separate code (per the roadmap "one dashboard + presets" principle).

**Key decisions that diverged from the original roadmap:**
- **LLM provider: Gemini** (`gemini-2.5-flash` via `google-genai` SDK), NOT Claude. Key in `.env` as `GEMINI_API_KEY`. ROADMAP §6 was updated to reflect this. `gemini-1.5-flash` is retired — use 2.5.
- **Resume = LaTeX.** User's real resume is a structured JSON schema (see [[resume-latex-pipeline]]) rendered to `.tex` and compiled to PDF by **tectonic**. There's an on-dashboard LaTeX editor (CodeMirror + live preview).
- **Sources (4):** RemoteOK (global JSON), Greenhouse, Lever, Ashby — the last three are per-company boards configured in `.env` (`GREENHOUSE_BOARDS`, `LEVER_BOARDS`, `ASHBY_BOARDS`). Defaults are mobile-heavy boards. Adding source #5 = one class in `core/sources/`.

**Sourcing/matching backlog batch (all built):**
- **Stale-job expiry:** `ingest_jobs` marks jobs of a source not seen in the run as `is_gone=True` (guarded by non-empty fetch). Lists already filter `is_gone=False`.
- **Cross-source dedupe:** `manage.py dedupe_jobs` groups live jobs by normalized (title, company) — strips seniority words — keeps the highest-score row as canonical, marks the rest `is_duplicate=True` / `duplicate_of=<canonical>`. Lists filter `is_duplicate=False`.
- **Embeddings (semantic matching):** `manage.py embed_jobs` embeds the profile + relevant jobs via Gemini `gemini-embedding-001` (3072-dim), stores `embedding` + cosine `semantic_score` on Job. **Free-tier quota is very low (~30/run, 429s after)** — command is resilient and resumes (only embeds `embedding__isnull`). Sort option "Best match (semantic)" orders by `semantic_score`. Keyword score remains the default relevance gate; semantic is a secondary signal.

**How to apply:** The roadmap is complete. Further work is "ongoing" Phase 5 territory (more adapters: Lever/Ashby/WWR — each is one new class in `core/sources/`) or polish. Confirm scope before large new features.

**Seed/run:** `python manage.py seed_profile` loads the real resume. `./setup.sh` (or `./start.sh`) runs setup + tmux + cron. `python manage.py ingest_jobs --source remoteok|greenhouse`.
