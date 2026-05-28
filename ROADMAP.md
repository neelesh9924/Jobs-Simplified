# Job Application Engine — Roadmap & Build Plan

> A local, single-user tool that **sources** relevant jobs from legitimate APIs, **scores** them against your profile, **tailors** your resume + cover letter per JD, and gives you a **review-and-submit queue** plus a tracking dashboard. A human (you) stays on the submit button.

---

## 1. What we're actually building (and what we're not)

### The thesis
The expensive parts of a job hunt are *sourcing* and *tailoring*. The cheap part is clicking "apply." So we **automate the expensive parts and keep a human on the submit button.** The success metric is **interviews**, not applications-submitted — so quality of each application matters more than volume.

### Core design principles (these govern every phase)
- **Flexible at the seams, rigid in the loop.** Pluggable adapters for job sources and for the LLM. One pipeline, one Job table, one dashboard. No speculative config knobs until a real need appears.
- **Human-in-the-loop on submit.** The tool prepares everything; you click submit. ~30s per role, quality stays high, zero account risk.
- **Structured data over blobs.** Resume lives as structured JSON, rendered to PDF from a template. Never mutate PDF blobs.
- **Idempotent + observable.** Re-running ingestion never duplicates. Every run is logged. You can always see what happened.

### Hard non-goals (do not build these — they will get accounts banned or are wasted effort)
- ❌ No automated **login/apply on LinkedIn, Naukri, Indeed**. ToS-violating, aggressive bot detection, asymmetric downside (losing your primary professional account mid-hunt). These are *manual discovery surfaces*; the tool handles everything *after* you find a role there.
- ❌ No **CAPTCHA / human-verification bypass**. If a source needs it, it's the wrong source.
- ❌ No **browser automation / headless scraping** (Playwright/Selenium). We target structured JSON/RSS endpoints only. Needing a headless browser is a signal the source is wrong, not a reason to add one.
- ❌ No **resume fabrication**. Tailoring = re-emphasis, keyword alignment, reordering. Never invent experience. You will get caught in interviews and it defeats the purpose.
- ❌ No **mass spray-apply**. Tailored applications to relevant roles beat generic volume.

### Geography reality (decided: support both, weighted honestly)
- **Remote / global:** strong auto-sourcing. Greenhouse, Lever, Ashby, Workable, WeWorkRemotely, RemoteOK expose clean APIs/feeds. The tool genuinely *finds* jobs for you here. High payoff.
- **India:** thin auto-sourcing. Most India roles route through Naukri/LinkedIn, which we deliberately don't scrape. For India the tool is a **tailoring + tracking + review engine** over roles *you* find manually — still valuable, just not a discovery engine.
- **Implication:** `region` is just a field; supporting both is free in the data model. But if most of your target roles are India on-site, weight your energy toward **Phase 3 (tailoring)** over **Phase 1–2 (sourcing)**.

---

## 2. Stack (locked)

| Concern | Choice | Why |
|---|---|---|
| Backend | **Django** | Free admin panel for inspecting Job/Application/ResumeVersion rows during dev; mature ORM + migrations. |
| DB | **SQLite** | Single user, single writer, local. One file you back up by copying. Postgres is pure overhead here. Django makes migration trivial *if* you ever multi-user it. |
| Frontend | **Django templates + HTMX + Alpine.js** | Server-rendered HTML with dynamic behavior (refresh queue, change status, live stats) via HTML fragments. No build step, no SPA, no separate API. Right tool for a single-user local dashboard. |
| Styling | **Tailwind via CDN** or plain CSS | No build pipeline. |
| Scheduling | **OS cron / Task Scheduler → `manage.py` commands** | Survives app restarts/crashes. More robust than in-app schedulers. No Celery/Redis (3 processes to babysit for nothing). |
| On-demand work (tailoring) | **Synchronous** | One user. Nobody cares if a request takes 8s. Add a light queue (**Django-Q2** or **Huey**, DB-backed) *only if* sync calls start annoying you. |
| HTTP / scraping | **httpx** (or requests) | Structured JSON/RSS endpoints only. |
| LLM | **Provider abstraction** (default: cloud API; fallback: local Ollama) | Same adapter pattern as sources. See §6. |

**Rejected on purpose:** FastAPI (lose the admin panel for marginal async gain), React/Vue/Flutter Web (architecture theater for one localhost user), Postgres (overhead), Celery+Redis (overhead), Playwright (wrong-source signal).

---

## 3. Architecture (the two seams that matter)

### Seam 1 — Source adapters
Every source implements one interface and normalizes into one `Job` table. Adding source #6 = writing one class.

```python
class JobSourceAdapter(ABC):
    source_key: str       # "remoteok", "greenhouse", "wwr"
    source_type: str      # "remote_board" | "ats"

    @abstractmethod
    def fetch(self, config: dict) -> Iterable[RawJob]: ...
    @abstractmethod
    def normalize(self, raw: RawJob) -> NormalizedJob: ...
```

### Seam 2 — LLM provider
Tailoring/cover-letter generation goes through a provider interface so cloud vs local is a config swap, not a rewrite.

```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, prompt: str, **kw) -> str: ...
```

### "Multiple dashboards" → one dashboard + filters + saved presets
"Startups board" and "Remote board" are the *same table* filtered by `source_type`. Don't build separate UI surfaces for two views of identical data. One dashboard + a filter bar (source, type, region, status, score) + **saved filter presets** = every "board" you described and any combination you invent later. **Saved presets ARE the "mix of configurations to experiment with" feature.**

### Data model (lean — 6 core tables, don't add more without a concrete need)

```
Profile          # single-user: structured resume JSON, skills[], prefs (regions, keywords, salary floor)
Job              # normalized job from any source; raw JSON kept; (source_key, external_id) unique
Application      # FK Job; status enum; FK tailored ResumeVersion; notes; applied_at; follow_up_at
ResumeVersion    # base or tailored; structured content + rendered file path; which provider made it
FilterPreset     # name + serialized filter params  (the "experiment configs")
IngestRun        # per-run log: source, started/finished, fetched/new/updated/errors  (stats + debugging)
```

`Application.status` enum: `new → interested → tailoring → ready → applied → screening → interview → offer → rejected / withdrawn`.

---

## 4. Edge cases & production risks to bake in from day one

- **Idempotent ingestion.** Upsert on `(source_key, external_id)`. Re-running must not duplicate. Track `last_seen_at`.
- **Stale/expired jobs.** Postings get pulled. If a job isn't seen in N runs, mark it `gone` (don't hard-delete — keep history).
- **Cross-source dedupe is hard.** Same role on Greenhouse *and* a remote board. Per-source dedup is exact (external_id); cross-source is fuzzy (normalized title+company). **Ship exact dedup first; add fuzzy later.** Don't over-invest early.
- **Region inference is messy.** Location strings are free text ("Remote (US)", "Bangalore/Remote"). Start with simple rules + a manual override field. Don't build an NLP pipeline for this.
- **Be polite to sources even with APIs.** Rate-limit, set a real User-Agent, cache. Getting IP-blocked from a *legitimate* source is an own-goal.
- **LLM key hygiene.** API key in env var, never committed. `.env` in `.gitignore` from commit #1.
- **Tailoring guardrail.** System prompt must forbid fabrication explicitly. Output must be diffable against the base resume so you can eyeball what changed.
- **PDF rendering.** Render from structured data → template → PDF (e.g. WeasyPrint/HTML-to-PDF). Never edit PDF bytes.

---

## 5. Phased plan

Each phase is built and verified before the next. Each is roughly one focused Claude Code session / PR-sized chunk.

### Phase 0 — Scaffold *(half a day)*
**Goal:** runnable skeleton, nothing clever.
- Django project + single app (`core`), SQLite, `.env` + `python-decouple`/`django-environ`, `.gitignore`.
- Base template + HTMX + Alpine + Tailwind CDN. One "hello" page that proves HTMX swaps work.
- `Profile` model + Django admin registered. Seed it with your real structured resume JSON.
- **Done when:** server runs, admin works, you've entered your profile, one HTMX fragment swaps live.

### Phase 1 — Data model + first source (the core loop, half-built) *(1–2 days)*
**Goal:** one real source ingests real jobs into the DB, idempotently, on a schedule.
- All 6 models + migrations + admin registration.
- `JobSourceAdapter` base class + **one concrete adapter** (default: **RemoteOK** — single public JSON endpoint, lowest friction to prove the loop; *verify the live endpoint/format at build time, don't trust this doc*).
- `manage.py ingest_jobs --source remoteok` management command: fetch → normalize → upsert → write `IngestRun`. Idempotent.
- Wire it to cron / Task Scheduler.
- **Done when:** running the command twice produces no dupes, `IngestRun` logs counts, jobs visible in admin. Adding a 2nd adapter would be obvious from the code.

### Phase 2 — Matching, filtering, ranking *(1–2 days)*
**Goal:** surface the *relevant* jobs, not all jobs.
- Scoring function: jobs scored against `Profile.skills` + keyword prefs (start with weighted keyword/skill overlap — **not** an LLM, **not** embeddings yet; cheap and explainable first).
- Dedupe (exact, per-source). Region inference (simple rules + override).
- Filterable, sortable job list view (HTMX). Filters: source, type, region, score, status.
- **Done when:** you open the list and the top results are genuinely roles you'd consider.

### Phase 3 — Resume tailoring + cover letters *(2–3 days, the real value)*
**Goal:** per-JD tailored resume + cover-letter draft, from structured data, no fabrication.
- `LLMProvider` interface + default provider (see §6). *Concrete provider to implement: `GeminiProvider` using `google-generativeai` SDK, model `gemini-1.5-flash`, key from `GEMINI_API_KEY` env var.*
- Tailoring service: base resume JSON + JD → re-emphasized/reordered resume JSON → render to PDF. Diff view vs base so you can see exactly what changed.
- Cover letter + screening-answer drafts.
- `ResumeVersion` records persist every tailored output, linked to the Job.
- **Done when:** click a job → get a tailored resume PDF + cover letter draft you'd actually send, and you can see the diff.

### Phase 4 — Dashboard *(1–2 days)*
**Goal:** one screen to run your hunt.
- Pipeline view by status (kanban-ish or grouped list), stats (applied this week, response rate, by source/region), follow-up reminders.
- Saved **FilterPresets** = your "experiment configs."
- Status transitions via HTMX (mark applied, move to interview, etc.).
- **Done when:** you can answer "what should I do today?" from one page.

### Phase 5 — Review-and-submit queue + more sources + follow-ups *(ongoing)*
**Goal:** the daily driver.
- Review queue: ready-to-submit roles with tailored docs attached. You review → mark applied (manual submit on the actual site). The queue is the 30-seconds-per-role surface.
- Add adapters #2–#5 (Greenhouse, Lever, Ashby, WWR) — each ~an afternoon now that the seam exists.
- Follow-up tracking + reminders (no auto-sending without your click).
- **Done when:** your daily flow is: open dashboard → review queue → submit a few → done.

### Backlog / future (deferred on purpose — don't pull these forward)
- Embedding-based semantic matching (only if keyword scoring proves too crude).
- Fuzzy cross-source dedup.
- Light background queue (Django-Q2/Huey) if synchronous tailoring gets annoying.
- Email-based follow-up *drafts* (drafts only; you send).
- Multi-profile / multi-resume-track support.
- Analytics on what gets responses (which keywords/sources/tailoring win).

---

## 6. The two open decisions (defaults baked in — override before you start)

**A. First source to implement.**
Default: **RemoteOK** (one public JSON endpoint = fastest path to a working loop). Source #2 = **Greenhouse** (target specific companies). Override if your highest-priority roles live elsewhere. *Whichever you pick, have Claude Code verify the live endpoint/format at build time — don't trust any hardcoded API shape in this doc.*

**B. LLM provider for tailoring.**
**Locked: Gemini 1.5 Flash via Google AI Studio free tier.** API key stored in `.env` as `GEMINI_API_KEY`. Never committed. AI Studio free tier is separate from a paid Gemini subscription — no billing required, 1500 req/day limit is well above single-user tailoring volume. Local Ollama remains a noted fallback if privacy becomes a concern.

---

## 7. How to drive Claude Code on this (per phase)

- **One phase at a time.** Don't ask it to build Phases 1–4 in one go; you'll get a sprawling rewrite you can't review.
- **Tell it to inspect before changing.** "Read the existing models/views/templates first, then make the smallest change that achieves X."
- **Constrain scope explicitly.** "Don't reformat unrelated code, don't rename things, don't delete files, preserve existing business logic."
- **Demand explanation + validation.** "After implementing, explain what changed and how to verify it, and give me the exact command to test it."
- **Keep prompts repo-aware but not hallucination-heavy.** Reference real files once they exist; don't invent paths.

### Paste-ready kickoff prompt (Phase 0 + start of Phase 1)
```
You are setting up a new Django project for a local, single-user job-application
tool. Read any existing files first; if the repo is empty, scaffold from scratch.

Build ONLY this, nothing more:
1. A Django project + single app `core`, using SQLite. Use django-environ for a
   .env file. Add .gitignore (ignore .env, db.sqlite3, __pycache__, venv).
2. Base template wired with HTMX, Alpine.js, and Tailwind via CDN. One page at /
   with a button that triggers an HTMX swap, to prove the frontend stack works.
3. A `Profile` model (single user): fields for structured resume data (JSONField),
   skills (JSON list), and prefs (JSON: regions, keywords, salary_floor).
   Register it in Django admin.

Constraints:
- Smallest working setup. No Celery, no Redis, no Postgres, no DRF, no React.
- Don't add models or features beyond the Profile model yet.
- Don't invent job-source logic yet.

After implementing: explain what you created, and give me the exact commands to
run migrations, create a superuser, and start the server so I can verify the
admin and the HTMX swap work.
```

---

*Open decisions to confirm before Phase 1: (A) first source, (B) LLM provider + your machine specs/privacy stance.*
