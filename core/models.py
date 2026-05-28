from django.db import models


class Profile(models.Model):
    structured_resume = models.JSONField(
        default=dict,
        help_text="Full resume as structured JSON (work, education, projects, etc.)",
    )
    skills = models.JSONField(
        default=list,
        help_text="Flat list of skill strings, e.g. ['Python', 'Django', 'SQL']",
    )
    prefs = models.JSONField(
        default=dict,
        help_text=(
            "Job search preferences: "
            "{'regions': [...], 'keywords': [...], 'salary_floor': 0}"
        ),
    )
    latex_source = models.TextField(
        blank=True,
        help_text="Hand-edited LaTeX. When set, it overrides the generated .tex for the base resume.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self):
        return f"Profile #{self.pk}"


class Job(models.Model):
    source_key = models.CharField(max_length=64)
    external_id = models.CharField(max_length=256)
    title = models.CharField(max_length=256)
    company = models.CharField(max_length=256)
    location = models.CharField(max_length=256, blank=True)
    region = models.CharField(max_length=64, blank=True)
    region_override = models.CharField(
        max_length=64, blank=True,
        help_text="Set manually to override inferred region",
    )
    url = models.URLField(max_length=512)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list)
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField()
    is_gone = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    # Cross-source dedupe: non-canonical copies point at the canonical row.
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )
    # Semantic matching (filled by the embed_jobs command).
    embedding = models.JSONField(null=True, blank=True)
    semantic_score = models.FloatField(null=True, blank=True)
    raw_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source_key", "external_id")]
        ordering = ["-posted_at"]

    def __str__(self):
        return f"{self.title} @ {self.company} [{self.source_key}]"


class ResumeVersion(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="resume_versions")
    job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="resume_versions"
    )
    label = models.CharField(max_length=128, help_text="e.g. 'base' or brief tailoring note")
    content = models.JSONField(default=dict, help_text="Structured resume content")
    rendered_path = models.CharField(max_length=512, blank=True, help_text="Path to rendered PDF")
    provider = models.CharField(max_length=64, blank=True, help_text="LLM provider that made this version")
    cover_letter = models.TextField(blank=True)
    screening_answers = models.JSONField(
        default=list, blank=True,
        help_text="List of {question, answer} drafts for application screening questions.",
    )
    latex_source = models.TextField(
        blank=True,
        help_text="Hand-edited LaTeX. When set, it overrides the generated .tex for this version.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ResumeVersion '{self.label}' (Profile #{self.profile_id})"


class Application(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        INTERESTED = "interested", "Interested"
        TAILORING = "tailoring", "Tailoring"
        READY = "ready", "Ready"
        APPLIED = "applied", "Applied"
        SCREENING = "screening", "Screening"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="application")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    resume_version = models.ForeignKey(
        ResumeVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications"
    )
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    followup_draft = models.TextField(blank=True, help_text="Drafted follow-up email (you send it).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Application: {self.job} [{self.status}]"


class FilterPreset(models.Model):
    name = models.CharField(max_length=128, unique=True)
    params = models.JSONField(default=dict, help_text="Serialized filter params")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class IngestRun(models.Model):
    source_key = models.CharField(max_length=64)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    fetched_count = models.IntegerField(default=0)
    new_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    gone_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    error_log = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"IngestRun {self.source_key} @ {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration_seconds(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def ok(self):
        return self.error_count == 0 and self.finished_at is not None
