import html
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Iterable

import httpx

from .base import JobSourceAdapter, NormalizedJob

USER_AGENT = "job-apply-engine/1.0 (personal automation tool)"


def _parse_dt(value):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class WeWorkRemotelyAdapter(JobSourceAdapter):
    source_key = "wwr"
    source_type = "remote_board"

    def __init__(self, feeds: list[str]):
        self.feeds = [f.strip() for f in feeds if f.strip()]

    def fetch(self) -> Iterable[NormalizedJob]:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
            for feed in self.feeds:
                resp = client.get(feed)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    nj = self._normalize(item)
                    if nj:
                        yield nj

    def _text(self, item, tag):
        el = item.find(tag)
        return (el.text or "").strip() if el is not None and el.text else ""

    def _normalize(self, item) -> NormalizedJob | None:
        link = self._text(item, "link") or self._text(item, "guid")
        raw_title = self._text(item, "title")
        if not link or not raw_title:
            return None
        # WWR titles are "Company: Role"
        if ":" in raw_title:
            company, title = raw_title.split(":", 1)
        else:
            company, title = "", raw_title
        region = self._text(item, "region")
        category = self._text(item, "category")
        return NormalizedJob(
            source_key=self.source_key,
            external_id=link,
            title=title.strip(),
            company=company.strip() or "Unknown",
            location=region,
            url=link,
            description=html.unescape(self._text(item, "description")),
            tags=[category] if category else [],
            posted_at=_parse_dt(self._text(item, "pubDate")),
            raw_data={"title": raw_title, "region": region, "category": category},
        )
