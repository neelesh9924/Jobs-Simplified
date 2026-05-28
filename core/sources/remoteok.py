from datetime import datetime, timezone
from typing import Iterable

import httpx

from .base import JobSourceAdapter, NormalizedJob

API_URL = "https://remoteok.com/api"
USER_AGENT = "job-apply-engine/1.0 (personal automation tool)"


class RemoteOKAdapter(JobSourceAdapter):
    source_key = "remoteok"
    source_type = "remote_board"

    def fetch(self) -> Iterable[NormalizedJob]:
        response = httpx.get(API_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        data = response.json()

        for item in data:
            # First element is a legal notice dict, not a job
            if "id" not in item:
                continue
            yield self._normalize(item)

    def _normalize(self, raw: dict) -> NormalizedJob:
        posted_at = None
        if raw.get("epoch"):
            posted_at = datetime.fromtimestamp(int(raw["epoch"]), tz=timezone.utc)

        salary_min = raw.get("salary_min") or None
        salary_max = raw.get("salary_max") or None
        # RemoteOK sends 0 when unknown; treat 0 as None
        if salary_min == 0:
            salary_min = None
        if salary_max == 0:
            salary_max = None

        return NormalizedJob(
            source_key=self.source_key,
            external_id=str(raw["id"]),
            title=raw.get("position", "").strip(),
            company=raw.get("company", "").strip(),
            location=raw.get("location", "").strip(),
            url=raw.get("url") or raw.get("apply_url", ""),
            description=raw.get("description", ""),
            tags=raw.get("tags") or [],
            salary_min=salary_min,
            salary_max=salary_max,
            posted_at=posted_at,
            raw_data=raw,
        )
