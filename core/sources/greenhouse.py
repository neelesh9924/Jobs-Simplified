import html
import time
from datetime import datetime
from typing import Iterable

import httpx

from .base import JobSourceAdapter, NormalizedJob

API_TMPL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
USER_AGENT = "job-apply-engine/1.0 (personal automation tool)"


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class GreenhouseAdapter(JobSourceAdapter):
    source_key = "greenhouse"
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
                time.sleep(0.5)  # be polite between boards

    def _normalize(self, board: str, raw: dict) -> NormalizedJob:
        departments = [d.get("name", "") for d in (raw.get("departments") or []) if d.get("name")]
        return NormalizedJob(
            source_key=self.source_key,
            # prefix with board so ids never collide across companies
            external_id=f"{board}:{raw['id']}",
            title=(raw.get("title") or "").strip(),
            company=(raw.get("company_name") or board).strip(),
            location=((raw.get("location") or {}).get("name") or "").strip(),
            url=raw.get("absolute_url", ""),
            description=html.unescape(raw.get("content") or ""),
            tags=departments,
            posted_at=_parse_dt(raw.get("first_published")) or _parse_dt(raw.get("updated_at")),
            raw_data=raw,
        )
