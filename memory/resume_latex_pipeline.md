---
name: resume-latex-pipeline
description: How the resume → LaTeX → PDF pipeline and on-dashboard editor work
metadata:
  type: project
---

The resume is structured JSON, rendered to LaTeX, compiled to PDF by **tectonic**.

**Schema** (`Profile.structured_resume`): name, title, contact{email,phone,github,linkedin}, summary, skill_groups[{label,items}], experience[{company,location,roles[{title,dates,bullets[]}]}], products{frontend_ownership,complex_domains}, projects[{name,bullets[]}], education[{degree,institution,dates}]. `Profile.skills` is a separate flat list used only by the keyword scorer.

**Renderer:** `core/services/latex_resume.py` builds the `.tex` string in Python (NOT a Django template — avoids `{{ }}`/LaTeX brace conflicts) with a `tex_escape()` for `& % _ ~ < >` etc. Parts joined with `""` (joining with `\n` injects blank lines and overflows the one-page layout). Mirrors the user's Overleaf template exactly (article, geometry 0.5in, tabularx for skills/education).

**Compile:** `core/services/pdf.py` — `compile_latex(tex)` runs tectonic via subprocess in a tempdir. `compile_resume_pdf(dict)` = render + compile.

**tectonic install gotcha:** `brew install tectonic` pulls llvm+rust and compiles from source (huge/slow). Instead the prebuilt binary was downloaded from GitHub releases to `/usr/local/bin/tectonic`. This is NOT declared in requirements/setup — a fresh machine needs it installed manually (user declined to harden this).

**Editing:** `latex_source` TextField on both Profile and ResumeVersion. When set (hand-edited via the editor), it overrides the generated `.tex` for previews + downloads. Editor at `/editor/<kind>/<pk>/` (kind = base|version): CodeMirror + iframe preview + Recompile (saves latex_source, returns inline PDF) + compile-error log.

**Tailoring** (`core/services/tailoring.py`): Gemini rewrites the structured schema (reorder/re-emphasize, no fabrication, preserves all keys), then renders to PDF. `diff_resumes()` compares base vs tailored section-by-section.
