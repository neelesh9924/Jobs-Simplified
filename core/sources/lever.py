import time
from datetime import datetime, timezone
from typing import Iterable

import httpx

from .base import JobSourceAdapter, NormalizedJob

API_TMPL = "https://api.lever.co/v0/postings/{board}?mode=json"
USER_AGENT = "job-apply-engine/1.0 (personal automation tool)"


class LeverAdapter(JobSourceAdapter):
    source_key = "lever"
    source_type = "ats"

    def __init__(self, boards: list[str]):
        self.boards = [b.strip() for b in boards if b.strip()]

    def fetch(self) -> Iterable[NormalizedJob]:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
            for board in self.boards:
                resp = client.get(API_TMPL.format(board=board))
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    for raw in data:
                        yield self._normalize(board, raw)
                time.sleep(0.5)

    def _normalize(self, board: str, raw: dict) -> NormalizedJob:
        cats = raw.get("categories") or {}
        posted_at = None
        if raw.get("createdAt"):
            posted_at = datetime.fromtimestamp(int(raw["createdAt"]) / 1000, tz=timezone.utc)
        tags = [t for t in (cats.get("team"), cats.get("commitment")) if t]
        return NormalizedJob(
            source_key=self.source_key,
            external_id=f"{board}:{raw['id']}",
            title=(raw.get("text") or "").strip(),
            company=board.replace("-", " ").title(),
            location=(cats.get("location") or "").strip(),
            url=raw.get("hostedUrl") or raw.get("applyUrl", ""),
            description=raw.get("description") or raw.get("descriptionPlain") or "",
            tags=tags,
            posted_at=posted_at,
            raw_data=raw,
        )
