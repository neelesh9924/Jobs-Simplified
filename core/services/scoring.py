"""
Relevance scoring — weighted keyword/skill overlap, zone-aware.

A match in the TITLE counts far more than one buried in the description, and
the profile's pref *keywords* (the role-defining terms like "android", "kotlin")
count more than generic *skills* (git, aws, …). Score saturates to 1.0.

Returns a float in [0.0, 1.0].
"""

import re

# Jobs scoring below this are hidden from the list by default (toggle to show all).
RELEVANCE_THRESHOLD = 0.25

# zone weights: (title, tags, description).
# Tags are weighted near-zero on purpose: some sources (RemoteOK) auto-attach
# noisy, irrelevant tags, so the title — where the role is actually named — drives
# relevance, with the description as a weaker secondary signal.
_KEYWORD_W = (6.0, 0.5, 1.0)
_SKILL_W = (2.0, 0.5, 0.3)
_SATURATION = 10.0  # raw weighted sum that maps to ~1.0


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z0-9#+.]+", text or "")}


def _matches(term: str, text_lower: str, token_set: set[str]) -> bool:
    # multi-word / punctuated terms -> substring; single tokens -> exact token
    if " " in term or "/" in term:
        return term in text_lower
    return term in token_set


def _zone_hit(term, title_l, title_t, tags_l, tags_t, desc_l, desc_t, weights):
    if _matches(term, title_l, title_t):
        return weights[0]
    if _matches(term, tags_l, tags_t):
        return weights[1]
    if _matches(term, desc_l, desc_t):
        return weights[2]
    return 0.0


def score_job(title: str, description: str, tags: list, skills: list, pref_keywords: list) -> float:
    keywords = {k.lower().strip() for k in pref_keywords if k.strip()}
    skillset = {s.lower().strip() for s in skills if s.strip()} - keywords
    if not keywords and not skillset:
        return 0.0

    tags_joined = " ".join(tags or [])
    title_l, tags_l, desc_l = (title or "").lower(), tags_joined.lower(), (description or "").lower()
    title_t, tags_t, desc_t = _tokens(title), _tokens(tags_joined), _tokens(description)

    raw = 0.0
    for kw in keywords:
        raw += _zone_hit(kw, title_l, title_t, tags_l, tags_t, desc_l, desc_t, _KEYWORD_W)
    for sk in skillset:
        raw += _zone_hit(sk, title_l, title_t, tags_l, tags_t, desc_l, desc_t, _SKILL_W)

    return round(min(1.0, raw / _SATURATION), 4)
