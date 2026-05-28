import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from core.models import Job

_NORM = re.compile(r"[^a-z0-9]+")
# Seniority/qualifier words stripped so "Senior Android Engineer" == "Android Engineer".
_NOISE = {"senior", "sr", "staff", "lead", "principal", "junior", "jr", "ii", "iii", "i", "the"}


def _norm(text: str) -> str:
    words = _NORM.sub(" ", (text or "").lower()).split()
    return " ".join(w for w in words if w not in _NOISE)


class Command(BaseCommand):
    help = "Mark cross-source duplicate jobs (same normalized title + company)."

    def handle(self, *args, **options):
        # reset, then recompute over live jobs
        Job.objects.exclude(is_duplicate=False, duplicate_of__isnull=True).update(
            is_duplicate=False, duplicate_of=None
        )

        groups = defaultdict(list)
        for job in Job.objects.filter(is_gone=False):
            groups[(_norm(job.title), _norm(job.company))].append(job)

        dup_count = 0
        for (t, c), jobs in groups.items():
            if not t or not c or len(jobs) < 2:
                continue
            # canonical = highest score, then earliest id (stable)
            canonical = sorted(jobs, key=lambda j: (-(j.score or 0), j.id))[0]
            for job in jobs:
                if job.id == canonical.id:
                    continue
                job.is_duplicate = True
                job.duplicate_of = canonical
                job.save(update_fields=["is_duplicate", "duplicate_of"])
                dup_count += 1

        self.stdout.write(self.style.SUCCESS(f"Marked {dup_count} duplicate(s) across {len(groups)} groups."))
