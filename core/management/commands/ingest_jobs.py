from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Job, IngestRun, Profile
from core.sources.remoteok import RemoteOKAdapter
from core.sources.greenhouse import GreenhouseAdapter
from core.sources.lever import LeverAdapter
from core.sources.ashby import AshbyAdapter
from core.sources.wwr import WeWorkRemotelyAdapter
from core.services.region import infer_region
from core.services.scoring import score_job

SOURCES = ["remoteok", "greenhouse", "lever", "ashby", "wwr"]


def _build_adapter(source_key):
    if source_key == "remoteok":
        return RemoteOKAdapter()
    if source_key == "greenhouse":
        return GreenhouseAdapter(boards=settings.GREENHOUSE_BOARDS)
    if source_key == "lever":
        return LeverAdapter(boards=settings.LEVER_BOARDS)
    if source_key == "ashby":
        return AshbyAdapter(boards=settings.ASHBY_BOARDS)
    if source_key == "wwr":
        return WeWorkRemotelyAdapter(feeds=settings.WWR_FEEDS)
    raise CommandError(f"Unknown source: {source_key}")


def _get_profile():
    return Profile.objects.first()


class Command(BaseCommand):
    help = "Fetch jobs from a source and upsert into the Job table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            required=True,
            choices=SOURCES,
            help="Source adapter to run",
        )

    def handle(self, *args, **options):
        source_key = options["source"]
        adapter = _build_adapter(source_key)
        profile = _get_profile()

        run = IngestRun.objects.create(source_key=source_key, started_at=timezone.now())
        errors = []

        try:
            jobs = list(adapter.fetch())
        except Exception as exc:
            run.error_count = 1
            run.error_log = str(exc)
            run.finished_at = timezone.now()
            run.save()
            raise CommandError(f"Fetch failed: {exc}") from exc

        run.fetched_count = len(jobs)
        new_count = 0
        updated_count = 0

        skills = profile.skills if profile else []
        pref_keywords = profile.prefs.get("keywords", []) if profile else []
        seen_ids = []

        for nj in jobs:
            try:
                region = infer_region(nj.location)
                job_score = score_job(nj.title, nj.description, nj.tags, skills, pref_keywords)

                obj, created = Job.objects.update_or_create(
                    source_key=nj.source_key,
                    external_id=nj.external_id,
                    defaults={
                        "title": nj.title,
                        "company": nj.company,
                        "location": nj.location,
                        "region": region,
                        "url": nj.url,
                        "description": nj.description,
                        "tags": nj.tags,
                        "salary_min": nj.salary_min,
                        "salary_max": nj.salary_max,
                        "posted_at": nj.posted_at,
                        "last_seen_at": timezone.now(),
                        "raw_data": nj.raw_data,
                        "is_gone": False,
                        "score": job_score,
                    },
                )
                if created:
                    new_count += 1
                else:
                    updated_count += 1
                seen_ids.append(nj.external_id)
            except Exception as exc:
                errors.append(f"{nj.external_id}: {exc}")

        # Stale-job expiry: mark a job gone only once it's been missing from the
        # last STALE_AFTER_RUNS runs of this source (forgiving of one bad fetch).
        # We need that many prior runs of history before expiring anything.
        gone_count = 0
        n = settings.STALE_AFTER_RUNS
        if seen_ids:
            prior = list(
                IngestRun.objects.filter(source_key=source_key)
                .exclude(pk=run.pk)
                .order_by("-started_at")[:n]
            )
            if len(prior) >= n:
                cutoff = prior[n - 1].started_at  # start of the run n-back
                gone_count = (
                    Job.objects.filter(source_key=source_key, is_gone=False, last_seen_at__lt=cutoff)
                    .update(is_gone=True)
                )

        run.new_count = new_count
        run.updated_count = updated_count
        run.gone_count = gone_count
        run.error_count = len(errors)
        run.error_log = "\n".join(errors)
        run.finished_at = timezone.now()
        run.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"[{source_key}] fetched={run.fetched_count} "
                f"new={new_count} updated={updated_count} gone={gone_count} errors={len(errors)}"
            )
        )
