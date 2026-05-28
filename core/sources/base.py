from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


@dataclass
class NormalizedJob:
    source_key: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    tags: list
    raw_data: dict
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None


class JobSourceAdapter(ABC):
    source_key: str
    source_type: str  # "remote_board" | "ats"

    @abstractmethod
    def fetch(self) -> Iterable[NormalizedJob]: ...
