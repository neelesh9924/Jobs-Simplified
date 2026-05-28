from django.core.management.base import BaseCommand

from core.models import Job, Profile
from core.services.region import infer_region
from core.services.scoring import score_job


class Command(BaseCommand):
    help = "Re-score and re-infer region for all jobs against the current Profile."

    def handle(self, *args, **options):
        profile = Profile.objects.first()
        if not profile:
            self.stdout.write(self.style.WARNING("No profile found — nothing to score against."))
            return

        skills = profile.skills
        pref_keywords = profile.prefs.get("keywords", [])

        jobs = Job.objects.all()
        updated = 0
        for job in jobs:
            region = job.region_override or infer_region(job.location)
            job_text = f"{job.title} {job.company} {job.description}"
            new_score = score_job(job_text, job.tags, skills, pref_keywords)
            job.region = region
            job.score = new_score
            updated += 1

        Job.objects.bulk_update(jobs, ["region", "score"])
        self.stdout.write(self.style.SUCCESS(f"Scored {updated} jobs."))
