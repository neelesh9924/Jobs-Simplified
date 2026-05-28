import math
import re
import time

from django.core.management.base import BaseCommand

from core.models import Job, Profile
from core.services.llm.gemini import GeminiProvider
from core.services.scoring import RELEVANCE_THRESHOLD

_TAGS = re.compile(r"<[^>]+>")


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _profile_text(p: Profile) -> str:
    r = p.structured_resume or {}
    parts = [r.get("title", ""), r.get("summary", ""), ", ".join(p.skills or [])]
    return " ".join(x for x in parts if x)


def _job_text(j: Job) -> str:
    desc = _TAGS.sub(" ", j.description or "")
    return f"{j.title}\n{j.company}\n{desc}"[:8000]


class Command(BaseCommand):
    help = "Compute semantic similarity (Gemini embeddings) for relevant jobs vs the profile."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=float, default=RELEVANCE_THRESHOLD,
                            help="Only embed jobs scoring >= this (keeps API usage bounded).")
        parser.add_argument("--reembed", action="store_true", help="Recompute even if already embedded.")

    def handle(self, *args, **options):
        profile = Profile.objects.first()
        if not profile:
            self.stdout.write(self.style.WARNING("No profile."))
            return

        provider = GeminiProvider()
        prof_vec = provider.embed(_profile_text(profile))

        qs = Job.objects.filter(is_gone=False, is_duplicate=False, score__gte=options["threshold"])
        if not options["reembed"]:
            qs = qs.filter(embedding__isnull=True)

        done = 0
        for job in qs:
            try:
                vec = provider.embed(_job_text(job))
                job.embedding = vec
                job.semantic_score = round(_cosine(prof_vec, vec), 4)
                job.save(update_fields=["embedding", "semantic_score"])
                done += 1
                time.sleep(0.2)  # gentle on rate limits
            except Exception as exc:
                self.stderr.write(f"  {job.id} {job.title[:40]}: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Embedded {done} jobs."))
