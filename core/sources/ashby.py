import time
from datetime import datetime
from typing import Iterable

import httpx

from .base import JobSourceAdapter, NormalizedJob

API_TMPL = "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
USER_AGENT = "job-apply-engine/1.0 (personal automation tool)"


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class AshbyAdapter(JobSourceAdapter):
    source_key = "ashby"
    source_type = "ats"

    def __init__(self, boards: list[str]):
        self.boards = [b.strip() for b in boards if b.strip()]

    def fetch(self) -> Iterable[NormalizedJob]:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
            for board in self.boards:
                resp = client.get(API_TMPL.format(board=board))
                resp.raise_for_status()
                for raw in resp.json().get("jobs", []):
                    yield self._normalize(board, raw)
                time.sleep(0.5)

    def _normalize(self, board: str, raw: dict) -> NormalizedJob:
        tags = [t for t in (raw.get("department"), raw.get("team")) if t]
        return NormalizedJob(
            source_key=self.source_key,
            external_id=f"{board}:{raw['id']}",
            title=(raw.get("title") or "").strip(),
            company=board.replace("-", " ").title(),
            location=(raw.get("location") or "").strip(),
            url=raw.get("jobUrl") or raw.get("applyUrl", ""),
            description=raw.get("descriptionHtml") or raw.get("descriptionPlain") or "",
            tags=tags,
            posted_at=_parse_dt(raw.get("publishedAt")),
            raw_data=raw,
        )
