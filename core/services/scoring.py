"""
Keyword/skill overlap scoring.

Score = fraction of profile terms found in the job text, weighted so that
skill matches count more than keyword-pref matches.

Returns a float in [0.0, 1.0].
"""

import re


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z0-9#+.]+", text)}


def score_job(job_text: str, job_tags: list, skills: list, pref_keywords: list) -> float:
    if not skills and not pref_keywords:
        return 0.0

    haystack = _tokens(job_text)
    tag_tokens = _tokens(" ".join(job_tags))
    haystack |= tag_tokens

    skill_tokens = [s.lower() for s in skills]
    kw_tokens = [k.lower() for k in pref_keywords]

    skill_hits = sum(1 for s in skill_tokens if s in haystack)
    kw_hits = sum(1 for k in kw_tokens if k in haystack)

    # Skills are weighted 2x over pref keywords
    total_weight = 2 * len(skill_tokens) + len(kw_tokens)
    if total_weight == 0:
        return 0.0

    weighted_hits = 2 * skill_hits + kw_hits
    return round(weighted_hits / total_weight, 4)
