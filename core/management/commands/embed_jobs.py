import math
import re
import time

from django.core.management.base import BaseCommand

from core.models import Job, Profile
from core.services.llm.gemini import GeminiProvider
from core.services.scoring import RELEVANCE_THRESHOLD

_TAGS = re.compile(r"<[^>]+>")
BATCH = 50            # texts per embed request — one API call per batch
MAX_RETRIES = 3


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _profile_text(p):
    r = p.structured_resume or {}
    parts = [r.get("title", ""), r.get("summary", ""), ", ".join(p.skills or [])]
    return " ".join(x for x in parts if x)


def _job_text(j):
    return f"{j.title}\n{j.company}\n{_TAGS.sub(' ', j.description or '')}"[:8000]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class Command(BaseCommand):
    help = "Compute semantic similarity (Gemini embeddings, batched) for relevant jobs vs the profile."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=float, default=RELEVANCE_THRESHOLD)
        parser.add_argument("--reembed", action="store_true")

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
        jobs = list(qs)

        done = 0
        for batch in _chunks(jobs, BATCH):
            texts = [_job_text(j) for j in batch]
            vecs = None
            for attempt in range(MAX_RETRIES):
                try:
                    vecs = provider.embed_batch(texts)
                    break
                except Exception as exc:
                    if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                        wait = 5 * (attempt + 1)
                        self.stderr.write(f"  rate-limited, retrying in {wait}s…")
                        time.sleep(wait)
                    else:
                        self.stderr.write(f"  batch failed: {str(exc)[:120]}")
                        break
            if not vecs:
                self.stdout.write(self.style.WARNING(f"Stopped early — embedded {done} (quota/error)."))
                return
            for job, vec in zip(batch, vecs):
                job.embedding = vec
                job.semantic_score = round(_cosine(prof_vec, vec), 4)
            Job.objects.bulk_update(batch, ["embedding", "semantic_score"])
            done += len(batch)
            time.sleep(0.3)

        self.stdout.write(self.style.SUCCESS(f"Embedded {done} jobs (batched)."))
