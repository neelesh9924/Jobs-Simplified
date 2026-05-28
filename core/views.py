import re
import uuid
from datetime import timedelta
from urllib.parse import urlencode

from django.db import models
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Job, Profile, ResumeVersion, Application, FilterPreset, IngestRun
from .services.tailoring import (
    tailor_resume, generate_cover_letter, diff_resumes,
    generate_screening_answers, generate_followup_email,
)
from .services.pdf import compile_latex, TectonicNotInstalled, LatexCompileError
from .services.latex_resume import render_latex
from .services.scoring import RELEVANCE_THRESHOLD, score_job
from .services.region import infer_region


def _param(request, key, default=""):
    """Read a filter param from either GET (filter form) or POST (hx-include on actions)."""
    return request.POST.get(key) or request.GET.get(key) or default


def _job_filter_options():
    base = Job.objects.filter(is_gone=False, is_duplicate=False)
    sources = sorted(base.order_by("source_key").values_list("source_key", flat=True).distinct())
    regions = sorted(base.exclude(region="").order_by("region").values_list("region", flat=True).distinct())
    return sources, regions


def index(request):
    return redirect("job_list")


def profile_view(request):
    profile = Profile.objects.first()
    if request.method == "POST" and profile:
        skills_raw = request.POST.get("skills", "")
        kw_raw = request.POST.get("keywords", "")
        regions_raw = request.POST.get("regions", "")
        salary = request.POST.get("salary_floor", "")
        profile.skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        prefs = dict(profile.prefs or {})
        prefs["keywords"] = [k.strip().lower() for k in kw_raw.split(",") if k.strip()]
        prefs["regions"] = [r.strip().lower() for r in regions_raw.split(",") if r.strip()]
        try:
            prefs["salary_floor"] = int(salary)
        except (TypeError, ValueError):
            prefs["salary_floor"] = 0
        profile.prefs = prefs
        profile.save()
        return redirect("profile")

    return render(request, "core/profile.html", {
        "active_nav": "profile",
        "profile": profile,
        "prefs": (profile.prefs or {}) if profile else {},
        "resume": (profile.structured_resume or {}) if profile else {},
    })


def htmx_ping(request):
    return render(request, "core/ping.html")


def job_list(request):
    ctx = _job_list_context(request)
    region = request.GET.get("region")
    if request.GET.get("tailored"):
        ctx["active_nav"] = "tailored"
    elif region == "remote":
        ctx["active_nav"] = "remote_view"
    elif region == "india":
        ctx["active_nav"] = "region_view"
    else:
        ctx["active_nav"] = "jobs"
    return render(request, "core/job_list.html", ctx)


def job_list_fragment(request):
    return render(request, "core/job_list_fragment.html", _job_list_context(request))


def _job_list_context(request):
    base_qs = Job.objects.filter(is_gone=False, is_duplicate=False)
    qs = base_qs

    source = request.GET.get("source", "")
    region = request.GET.get("region", "")
    status = request.GET.get("status", "")
    min_score = request.GET.get("min_score", "")
    tailored = request.GET.get("tailored", "")
    show_all = request.GET.get("all", "")
    posted = request.GET.get("posted", "")
    q = request.GET.get("q", "")

    # Relevance gate: hide low-scoring jobs by default unless "show all" is on.
    if not show_all:
        qs = qs.filter(score__gte=RELEVANCE_THRESHOLD)
    if posted in ("7", "15", "30"):
        qs = qs.filter(posted_at__gte=timezone.now() - timedelta(days=int(posted)))

    if source:
        qs = qs.filter(source_key=source)
    if region:
        qs = qs.filter(Q(region=region) | Q(region_override=region))
    if status == "new":
        qs = qs.exclude(application__isnull=False)
    elif status:
        qs = qs.filter(application__status=status)
    if tailored:
        qs = qs.filter(resume_versions__isnull=False).distinct()
    if min_score:
        try:
            qs = qs.filter(score__gte=float(min_score))
        except ValueError:
            pass
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(company__icontains=q) | Q(description__icontains=q)
        )

    # Sorting is split into two independent controls:
    #   match = score-based ordering (the dropdown): -score | -semantic_score | score
    #   sort  = optional column sort (the table headers): posted_at | -posted_at | company | -company
    # A column sort, when present, takes precedence over the match mode.
    match = request.GET.get("match", "-score")
    if match not in ("-score", "-semantic_score", "score"):
        match = "-score"
    column_sort = request.GET.get("sort", "")
    if column_sort in ("posted_at", "-posted_at", "company", "-company"):
        qs = qs.order_by(column_sort)
        active_sort = column_sort
    elif match == "-semantic_score":
        qs = qs.order_by(models.F("semantic_score").desc(nulls_last=True))
        active_sort = match
    else:
        qs = qs.order_by(match)
        active_sort = match

    jobs = list(qs[:200])
    max_score = max((j.score or 0) for j in jobs) if jobs else 0

    # .order_by() clears the model's default ordering — otherwise Django adds
    # posted_at to the SELECT and DISTINCT no longer collapses duplicates.
    sources = base_qs.order_by("source_key").values_list("source_key", flat=True).distinct()
    regions = base_qs.exclude(region="").order_by("region").values_list("region", flat=True).distinct()

    stats = {
        "total": base_qs.count(),
        "relevant": base_qs.filter(score__gte=RELEVANCE_THRESHOLD).count(),
        "tailored": base_qs.filter(resume_versions__isnull=False).distinct().count(),
        "applied": base_qs.filter(application__status="applied").count(),
    }

    return {
        "jobs": jobs,
        "total": qs.count(),
        "max_score": max_score or 1,
        "stats": stats,
        "sources": sorted(sources),
        "regions": sorted(regions),
        "presets": [
            {"id": p.id, "name": p.name, "qs": urlencode(p.params)}
            for p in FilterPreset.objects.all()
        ],
        "filters": {
            "source": source,
            "region": region,
            "status": status,
            "min_score": min_score,
            "tailored": tailored,
            "all": show_all,
            "posted": posted,
            "q": q,
            "match": match,
            "sort": column_sort,
            "active_sort": active_sort,
        },
    }


REGION_CHOICES = ["remote", "india", "us", "europe", "other"]


def add_job(request):
    """Manually add a job (e.g. one found on LinkedIn/Naukri) into the pipeline."""
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        company = (request.POST.get("company") or "").strip()
        if title and company:
            profile = Profile.objects.first()
            skills = profile.skills if profile else []
            keywords = profile.prefs.get("keywords", []) if profile else []
            location = (request.POST.get("location") or "").strip()
            region = (request.POST.get("region") or "").strip()
            description = (request.POST.get("description") or "").strip()
            job = Job.objects.create(
                source_key="manual",
                external_id=f"manual:{uuid.uuid4().hex}",
                title=title,
                company=company,
                location=location,
                region=region or infer_region(location),
                url=(request.POST.get("url") or "").strip(),
                description=description,
                tags=[],
                last_seen_at=timezone.now(),
                posted_at=timezone.now(),
                score=score_job(title, description, [], skills, keywords),
            )
            # A manually-added job is one you intend to pursue → start it in the pipeline.
            Application.objects.get_or_create(job=job, defaults={"status": Application.Status.INTERESTED})
            return redirect("job_detail", job_id=job.id)
    return render(request, "core/add_job.html", {"active_nav": "jobs", "regions": REGION_CHOICES})


def job_detail(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    return render(request, "core/job_detail.html", {
        "job": job,
        "active_nav": "jobs",
        "app": Application.objects.filter(job=job).first(),
        "all_statuses": MOVABLE_STATUSES,
        **_tailor_panel_context(job),
    })


def _tailor_panel_context(job):
    versions = job.resume_versions.order_by("-created_at")
    latest = versions.first()
    diff = None
    if latest:
        profile = Profile.objects.first()
        base = profile.structured_resume if profile else {}
        diff = diff_resumes(base, latest.content)
    return {"versions": versions, "latest": latest, "diff": diff}


@require_POST
def tailor_job(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    profile = Profile.objects.first()

    if profile:
        tailored = tailor_resume(
            base_resume=profile.structured_resume,
            job_title=job.title,
            job_description=job.description,
        )
        cover = generate_cover_letter(
            tailored_resume=tailored,
            job_title=job.title,
            company=job.company,
            job_description=job.description,
        )
        screening = generate_screening_answers(
            tailored_resume=tailored,
            job_title=job.title,
            company=job.company,
            job_description=job.description,
        )
        ResumeVersion.objects.create(
            profile=profile,
            job=job,
            label=f"Tailored for {job.company}",
            content=tailored,
            provider="gemini-2.5-flash",
            cover_letter=cover,
            screening_answers=screening,
        )
        # Advance the pipeline: tailoring a resume means you're working on it.
        # Don't downgrade jobs already further along (ready/applied/etc.).
        app, _ = Application.objects.get_or_create(job=job)
        if app.status in (S.NEW, S.INTERESTED):
            app.status = S.TAILORING
            app.save(update_fields=["status"])

    if request.headers.get("HX-Request"):
        return render(request, "core/_tailor_panel.html", {"job": job, **_tailor_panel_context(job)})
    return redirect("job_detail", job_id=job_id)


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_") or "Resume"


class _Target:
    """Unifies the base resume (Profile) and a tailored ResumeVersion behind one API."""

    def __init__(self, kind, obj):
        self.kind = kind
        self.obj = obj

    @property
    def structured(self):
        return self.obj.structured_resume if self.kind == "base" else self.obj.content

    @property
    def latex(self):
        """Hand-edited LaTeX if present, else freshly generated from structured data."""
        return self.obj.latex_source or render_latex(self.structured)

    def save_latex(self, tex):
        self.obj.latex_source = tex
        self.obj.save(update_fields=["latex_source"])

    @property
    def filename(self):
        name = _slug((self.structured or {}).get("name"))
        if self.kind == "base":
            return f"{name}_Resume.pdf"
        company = _slug(self.obj.job.company if self.obj.job else "resume")
        return f"{name}_{company}.pdf"

    @property
    def title(self):
        if self.kind == "base":
            return "Base résumé"
        return self.obj.label


def _resolve_target(kind, pk):
    if kind == "version":
        return _Target("version", get_object_or_404(ResumeVersion, pk=pk))
    profile = Profile.objects.first()
    if not profile:
        raise Http404("No profile")
    return _Target("base", profile)


def _compile_response(tex, filename, *, inline):
    try:
        pdf = compile_latex(tex)
    except TectonicNotInstalled as exc:
        return HttpResponse(f"PDF engine not installed.\n\n{exc}", status=503, content_type="text/plain")
    except LatexCompileError as exc:
        return HttpResponse(f"LaTeX failed to compile.\n\n{exc}", status=422, content_type="text/plain")
    resp = HttpResponse(pdf, content_type="application/pdf")
    disp = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f'{disp}; filename="{filename}"'
    return resp


def resume_pdf(request, version_id):
    target = _Target("version", get_object_or_404(ResumeVersion, pk=version_id))
    return _compile_response(target.latex, target.filename, inline=False)


def base_resume_pdf(request):
    target = _resolve_target("base", None)
    return _compile_response(target.latex, target.filename, inline=False)


def editor(request, kind, pk=0):
    target = _resolve_target(kind, pk)
    return render(request, "core/editor.html", {
        "active_nav": "editor",
        "kind": target.kind,
        "pk": target.obj.pk,
        "title": target.title,
        "latex": target.latex,
        "edited": bool(target.obj.latex_source),
        "obj_job_id": target.obj.job_id if target.kind == "version" else None,
    })


def editor_preview(request, kind, pk=0):
    target = _resolve_target(kind, pk)
    return _compile_response(target.latex, target.filename, inline=True)


@require_POST
def editor_compile(request, kind, pk=0):
    target = _resolve_target(kind, pk)
    tex = request.POST.get("latex", "")
    target.save_latex(tex)
    return _compile_response(tex, target.filename, inline=True)


# ----------------------------------------------------------------------------
# Phase 4 — Dashboard / Tracker
# ----------------------------------------------------------------------------

S = Application.Status

# Active pipeline stages shown as kanban columns, in order.
STAGE_META = [
    {"key": S.INTERESTED, "label": "Interested", "dot": "bg-slate-400"},
    {"key": S.TAILORING,  "label": "Tailoring",  "dot": "bg-amber-400"},
    {"key": S.READY,      "label": "Ready",      "dot": "bg-brand-500"},
    {"key": S.APPLIED,    "label": "Applied",    "dot": "bg-blue-500"},
    {"key": S.SCREENING,  "label": "Screening",  "dot": "bg-cyan-500"},
    {"key": S.INTERVIEW,  "label": "Interview",  "dot": "bg-violet-500"},
    {"key": S.OFFER,      "label": "Offer",      "dot": "bg-emerald-500"},
]
CLOSED_STAGES = [S.REJECTED, S.WITHDRAWN]
RESPONDED_STAGES = [S.SCREENING, S.INTERVIEW, S.OFFER]
FOLLOWUP_STAGES = [S.APPLIED, S.SCREENING, S.INTERVIEW]

# Status choices offered in the Move menu — exclude NEW (the "no application" state).
MOVABLE_STATUSES = [(v, l) for v, l in Application.Status.choices if v != S.NEW]


_APP_SORTS = {
    "-score": "-job__score",
    "score": "job__score",
    "-updated_at": "-updated_at",
    "-posted_at": "-job__posted_at",
}


def _filter_apps(qs, request):
    q = _param(request, "q")
    source = _param(request, "source")
    region = _param(request, "region")
    posted = _param(request, "posted")
    if q:
        qs = qs.filter(Q(job__title__icontains=q) | Q(job__company__icontains=q))
    if source:
        qs = qs.filter(job__source_key=source)
    if region:
        qs = qs.filter(Q(job__region=region) | Q(job__region_override=region))
    if posted in ("7", "15", "30"):
        qs = qs.filter(job__posted_at__gte=timezone.now() - timedelta(days=int(posted)))
    return qs


def _build_board(request):
    sort = _param(request, "sort", "-score")
    order = _APP_SORTS.get(sort, "-job__score")
    apps = list(_filter_apps(Application.objects.select_related("job"), request).order_by(order))

    by_status = {}
    for app in apps:
        by_status.setdefault(app.status, []).append(app)

    columns = [
        {**meta, "apps": by_status.get(meta["key"], []), "count": len(by_status.get(meta["key"], []))}
        for meta in STAGE_META
    ]
    closed = [a for a in apps if a.status in CLOSED_STAGES]
    sources, regions = _job_filter_options()
    return {
        "columns": columns,
        "closed": closed,
        "all_statuses": MOVABLE_STATUSES,
        "sources": sources,
        "regions": regions,
        "filters": {
            "q": _param(request, "q"),
            "source": _param(request, "source"),
            "region": _param(request, "region"),
            "posted": _param(request, "posted"),
            "sort": sort,
        },
    }


def _tracker_stats():
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    qs = Application.objects.all()
    applied_total = qs.filter(applied_at__isnull=False).count()
    responded = qs.filter(status__in=RESPONDED_STAGES).count()
    return {
        "active": qs.exclude(status__in=CLOSED_STAGES).count(),
        "applied_week": qs.filter(applied_at__gte=week_ago).count(),
        "response_rate": round(100 * responded / applied_total) if applied_total else 0,
        "followups_due": qs.filter(follow_up_at__lte=now, status__in=FOLLOWUP_STAGES).count(),
    }


def tracker(request):
    return render(request, "core/tracker.html", {
        "active_nav": "tracker",
        "stats": _tracker_stats(),
        **_build_board(request),
    })


def tracker_fragment(request):
    return render(request, "core/_board.html", {"stats": _tracker_stats(), **_build_board(request)})


@require_POST
def set_status(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    status = request.POST.get("status", "")
    scope = request.POST.get("scope", "")

    if status == "remove":
        Application.objects.filter(job=job).delete()
    elif status in Application.Status.values:
        app, _ = Application.objects.get_or_create(job=job)
        app.status = status
        if status == S.APPLIED and not app.applied_at:
            app.applied_at = timezone.now()
            if not app.follow_up_at:
                app.follow_up_at = timezone.now() + timedelta(days=7)
        app.save()

    if request.headers.get("HX-Request"):
        if scope == "detail":
            return render(request, "core/_status_widget.html", {
                "job": job,
                "app": Application.objects.filter(job=job).first(),
                "all_statuses": MOVABLE_STATUSES,
            })
        if scope == "queue":
            return render(request, "core/_queue.html", _queue_context(request))
        return render(request, "core/_board.html", {"stats": _tracker_stats(), **_build_board(request)})
    return redirect("tracker")


# ----------------------------------------------------------------------------
# Filter presets (saved job-list filter configs)
# ----------------------------------------------------------------------------

_PRESET_PARAMS = ["q", "source", "region", "status", "sort", "tailored", "min_score"]


@require_POST
def save_preset(request):
    name = (request.POST.get("name") or "").strip()
    if name:
        params = {k: v for k in _PRESET_PARAMS if (v := request.POST.get(k))}
        FilterPreset.objects.update_or_create(name=name, defaults={"params": params})
    return redirect(request.POST.get("next") or "job_list")


@require_POST
def delete_preset(request, preset_id):
    FilterPreset.objects.filter(pk=preset_id).delete()
    return redirect(request.POST.get("next") or "job_list")


# ----------------------------------------------------------------------------
# Phase 5 — Review-and-submit queue + follow-ups
# ----------------------------------------------------------------------------

def _queue_context(request=None):
    now = timezone.now()
    sort = _param(request, "sort", "-score") if request else "-score"
    order = _APP_SORTS.get(sort, "-job__score")

    ready = _filter_apps(Application.objects.select_related("job").filter(status=S.READY), request) if request \
        else Application.objects.select_related("job").filter(status=S.READY)
    ready = ready.order_by(order)
    followups = (Application.objects.select_related("job")
                 .filter(follow_up_at__lte=now, status__in=FOLLOWUP_STAGES)
                 .order_by("follow_up_at"))
    sources, regions = _job_filter_options()
    return {
        "ready": ready,
        "followups": followups,
        "ready_count": ready.count(),
        "followups_count": followups.count(),
        "all_statuses": MOVABLE_STATUSES,
        "sources": sources,
        "regions": regions,
        "filters": {
            "q": _param(request, "q") if request else "",
            "source": _param(request, "source") if request else "",
            "region": _param(request, "region") if request else "",
            "posted": _param(request, "posted") if request else "",
            "sort": sort,
        },
    }


def queue(request):
    return render(request, "core/queue.html", {"active_nav": "queue", **_queue_context(request)})


def queue_fragment(request):
    return render(request, "core/_queue.html", _queue_context(request))


# ----------------------------------------------------------------------------
# Scraper / ingestion observability
# ----------------------------------------------------------------------------

def _ingestion_context(request):
    runs = IngestRun.objects.all()
    source = request.GET.get("source", "")
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")
    sort = request.GET.get("sort", "-started_at")

    if source:
        runs = runs.filter(source_key=source)
    if date_from:
        runs = runs.filter(started_at__date__gte=date_from)
    if date_to:
        runs = runs.filter(started_at__date__lte=date_to)

    allowed = {"-started_at", "started_at", "-new_count", "-error_count", "-fetched_count"}
    if sort not in allowed:
        sort = "-started_at"
    runs = runs.order_by(sort)

    run_sources = list(IngestRun.objects.order_by("source_key").values_list("source_key", flat=True).distinct())
    job_sources = list(Job.objects.order_by("source_key").values_list("source_key", flat=True).distinct())
    all_sources = sorted(set(run_sources) | set(job_sources))

    platforms = []
    for sk in all_sources:
        sk_runs = IngestRun.objects.filter(source_key=sk)
        agg = sk_runs.aggregate(new=models.Sum("new_count"), err=models.Sum("error_count"))
        platforms.append({
            "source": sk,
            "live_jobs": Job.objects.filter(source_key=sk, is_gone=False).count(),
            "gone_jobs": Job.objects.filter(source_key=sk, is_gone=True).count(),
            "total_runs": sk_runs.count(),
            "total_new": agg["new"] or 0,
            "total_err": agg["err"] or 0,
            "last": sk_runs.order_by("-started_at").first(),
        })

    totals = {
        "runs": IngestRun.objects.count(),
        "live_jobs": Job.objects.filter(is_gone=False, is_duplicate=False).count(),
        "last_run": IngestRun.objects.order_by("-started_at").first(),
        "errors": IngestRun.objects.exclude(error_count=0).count(),
    }

    from .management.commands.ingest_jobs import SOURCES

    return {
        "runs": runs[:200],
        "run_total": runs.count(),
        "platforms": platforms,
        "totals": totals,
        "sources": run_sources,
        "run_targets": SOURCES,
        "filters": {"source": source, "from": date_from, "to": date_to, "sort": sort},
    }


def ingestion(request):
    return render(request, "core/ingestion.html", {"active_nav": "ingestion", **_ingestion_context(request)})


@require_POST
def run_ingest(request):
    """Trigger ingestion from the UI (synchronous — single-user, local)."""
    from django.core.management import call_command
    from .management.commands.ingest_jobs import SOURCES

    source = request.POST.get("source", "")
    targets = SOURCES if source in ("", "all") else [source]
    for s in targets:
        try:
            call_command("ingest_jobs", source=s)
        except Exception:
            # fetch failures are already logged to an IngestRun row; keep going
            pass
    try:
        call_command("dedupe_jobs")
    except Exception:
        pass
    return redirect("ingestion")


def ingestion_fragment(request):
    return render(request, "core/_ingestion_fragment.html", _ingestion_context(request))


@require_POST
def snooze_followup(request, job_id):
    app = get_object_or_404(Application, job_id=job_id)
    base = app.follow_up_at or timezone.now()
    base = max(base, timezone.now())
    app.follow_up_at = base + timedelta(days=7)
    app.save(update_fields=["follow_up_at"])
    if request.headers.get("HX-Request"):
        return render(request, "core/_queue.html", _queue_context(request))
    return redirect("queue")


@require_POST
def followup_draft(request, job_id):
    app = get_object_or_404(Application, job_id=job_id)
    profile = Profile.objects.first()
    days = 0
    if app.applied_at:
        days = max(0, (timezone.now() - app.applied_at).days)
    app.followup_draft = generate_followup_email(
        resume=profile.structured_resume if profile else {},
        job_title=app.job.title,
        company=app.job.company,
        applied_days_ago=days,
    )
    app.save(update_fields=["followup_draft"])
    return render(request, "core/_followup_draft.html", {"app": app})
