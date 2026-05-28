import json
import re

from .llm.gemini import GeminiProvider

_SYSTEM = """You are a resume tailoring assistant for a software engineer.

You receive a structured resume as JSON and a job description. Re-emphasize the
resume for that specific role.

RULES — follow strictly:
1. NEVER invent, add, or fabricate experience, skills, companies, dates, metrics,
   or achievements not already present in the input resume.
2. Only REORDER bullet points within a role, ADJUST emphasis, and REPHRASE existing
   content to align with the job's language. You may reorder skill groups and the
   items within them, but only using skills already present.
3. Keep the EXACT same JSON schema and keys as the input. Do not add or remove keys.
   Preserve every company, role, project, and education entry. Keep bullet counts
   the same (reorder/rephrase, don't drop or add).
4. Do not touch the "contact", "name", or dates. You may lightly adjust "title" and
   "summary" wording to match the role, without inventing new facts.
5. Return ONLY the valid JSON object. No explanation, no markdown fences.
"""

_COVER_SYSTEM = """You are a professional cover letter writer.

RULES:
1. Base the letter only on information present in the provided resume — do not fabricate.
2. Write 3 short paragraphs: (1) why this role, (2) most relevant experience/skills,
   (3) closing.
3. Keep it under 250 words. Professional but direct tone.
4. Return plain text only — no markdown, no headers, no subject line, no signature block.
"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text.strip())


def tailor_resume(base_resume: dict, job_title: str, job_description: str) -> dict:
    prompt = (
        f"JOB TITLE: {job_title}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:5000]}\n\n"
        f"RESUME (JSON):\n{json.dumps(base_resume, indent=2)}\n\n"
        "Return the tailored resume JSON now."
    )
    provider = GeminiProvider()
    raw = provider.complete(_SYSTEM, prompt)
    tailored = _extract_json(raw)
    # Defensive: never let the model drop contact info.
    if base_resume.get("contact") and not tailored.get("contact"):
        tailored["contact"] = base_resume["contact"]
    return tailored


def generate_cover_letter(tailored_resume: dict, job_title: str, company: str, job_description: str) -> str:
    prompt = (
        f"ROLE: {job_title} at {company}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:2500]}\n\n"
        f"MY RESUME:\n{json.dumps(tailored_resume, indent=2)}\n\n"
        "Write the cover letter now."
    )
    provider = GeminiProvider()
    return provider.complete(_COVER_SYSTEM, prompt).strip()


def _join(val) -> str:
    if isinstance(val, list):
        return "\n".join(f"• {v}" for v in val)
    return str(val) if val else ""


def diff_resumes(base: dict, tailored: dict) -> list[dict]:
    """Section-by-section comparison for the diff view."""
    base = base or {}
    tailored = tailored or {}
    rows = []

    def add(section, b, t):
        b, t = (b or "").strip(), (t or "").strip()
        if b or t:
            rows.append({"section": section, "base": b, "tailored": t, "changed": b != t})

    add("Title", str(base.get("title", "")), str(tailored.get("title", "")))
    add("Summary", str(base.get("summary", "")), str(tailored.get("summary", "")))

    # Experience — match by company + role index
    for i, comp_b in enumerate(base.get("experience", []) or []):
        comp_t = (tailored.get("experience", []) or [{}] * (i + 1))[i] if i < len(tailored.get("experience", []) or []) else {}
        company = comp_b.get("company", f"Company {i+1}")
        for j, role_b in enumerate(comp_b.get("roles", []) or []):
            roles_t = comp_t.get("roles", []) or []
            role_t = roles_t[j] if j < len(roles_t) else {}
            label = role_b.get("title") or "Role"
            add(f"{company} — {label}", _join(role_b.get("bullets", [])), _join(role_t.get("bullets", [])))

    # Skill groups
    for i, grp_b in enumerate(base.get("skill_groups", []) or []):
        grps_t = tailored.get("skill_groups", []) or []
        grp_t = grps_t[i] if i < len(grps_t) else {}
        add(f"Skills — {grp_b.get('label','')}", str(grp_b.get("items", "")), str(grp_t.get("items", "")))

    # Products
    pb, pt = base.get("products", {}) or {}, tailored.get("products", {}) or {}
    add("Products — Frontend Ownership", pb.get("frontend_ownership", ""), pt.get("frontend_ownership", ""))
    add("Products — Complex Domains", pb.get("complex_domains", ""), pt.get("complex_domains", ""))

    # Projects
    for i, proj_b in enumerate(base.get("projects", []) or []):
        projs_t = tailored.get("projects", []) or []
        proj_t = projs_t[i] if i < len(projs_t) else {}
        add(f"Project — {proj_b.get('name','')}", _join(proj_b.get("bullets", [])), _join(proj_t.get("bullets", [])))

    return rows
