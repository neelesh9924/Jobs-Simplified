from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Job, IngestRun, Profile
from core.sources.remoteok import RemoteOKAdapter
from core.sources.greenhouse import GreenhouseAdapter
from core.services.region import infer_region
from core.services.scoring import score_job

SOURCES = ["remoteok", "greenhouse"]


def _build_adapter(source_key):
    if source_key == "remoteok":
        return RemoteOKAdapter()
    if source_key == "greenhouse":
        return GreenhouseAdapter(boards=settings.GREENHOUSE_BOARDS)
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

        for nj in jobs:
            try:
                region = infer_region(nj.location)
                job_text = f"{nj.title} {nj.company} {nj.description}"
                job_score = score_job(job_text, nj.tags, skills, pref_keywords)

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
            except Exception as exc:
                errors.append(f"{nj.external_id}: {exc}")

        run.new_count = new_count
        run.updated_count = updated_count
        run.error_count = len(errors)
        run.error_log = "\n".join(errors)
        run.finished_at = timezone.now()
        run.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"[{source_key}] fetched={run.fetched_count} "
                f"new={new_count} updated={updated_count} errors={len(errors)}"
            )
        )
