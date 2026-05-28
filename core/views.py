import re
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Job, Profile, ResumeVersion, Application, FilterPreset
from .services.tailoring import tailor_resume, generate_cover_letter, diff_resumes
from .services.pdf import compile_latex, TectonicNotInstalled, LatexCompileError
from .services.latex_resume import render_latex


def index(request):
    return redirect("job_list")


def htmx_ping(request):
    return render(request, "core/ping.html")


def job_list(request):
    ctx = _job_list_context(request)
    ctx["active_nav"] = "tailored" if request.GET.get("tailored") else "jobs"
    return render(request, "core/job_list.html", ctx)


def job_list_fragment(request):
    return render(request, "core/job_list_fragment.html", _job_list_context(request))


def _job_list_context(request):
    base_qs = Job.objects.filter(is_gone=False)
    qs = base_qs

    source = request.GET.get("source", "")
    region = request.GET.get("region", "")
    status = request.GET.get("status", "")
    min_score = request.GET.get("min_score", "")
    tailored = request.GET.get("tailored", "")
    q = request.GET.get("q", "")

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

    sort = request.GET.get("sort", "-score")
    allowed_sorts = {"score", "-score", "posted_at", "-posted_at", "company", "-company"}
    if sort not in allowed_sorts:
        sort = "-score"
    qs = qs.order_by(sort)

    jobs = list(qs[:200])
    max_score = max((j.score or 0) for j in jobs) if jobs else 0

    # .order_by() clears the model's default ordering — otherwise Django adds
    # posted_at to the SELECT and DISTINCT no longer collapses duplicates.
    sources = base_qs.order_by("source_key").values_list("source_key", flat=True).distinct()
    regions = base_qs.exclude(region="").order_by("region").values_list("region", flat=True).distinct()

    stats = {
        "total": base_qs.count(),
        "scored": base_qs.exclude(score__isnull=True).count(),
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
            "q": q,
            "sort": sort,
        },
    }


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
        ResumeVersion.objects.create(
            profile=profile,
            job=job,
            label=f"Tailored for {job.company}",
            content=tailored,
            provider="gemini-2.5-flash",
            cover_letter=cover,
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


def _build_board():
    apps = list(Application.objects.select_related("job").all())
    by_status = {}
    for app in apps:
        by_status.setdefault(app.status, []).append(app)

    columns = [
        {**meta, "apps": by_status.get(meta["key"], []), "count": len(by_status.get(meta["key"], []))}
        for meta in STAGE_META
    ]
    closed = [a for a in apps if a.status in CLOSED_STAGES]
    return {"columns": columns, "closed": closed, "all_statuses": MOVABLE_STATUSES}


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
        **_build_board(),
    })


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
            return render(request, "core/_queue.html", _queue_context())
        return render(request, "core/_board.html", {"stats": _tracker_stats(), **_build_board()})
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

def _queue_context():
    now = timezone.now()
    ready = (Application.objects.select_related("job")
             .filter(status=S.READY).order_by("-job__score"))
    followups = (Application.objects.select_related("job")
                 .filter(follow_up_at__lte=now, status__in=FOLLOWUP_STAGES)
                 .order_by("follow_up_at"))
    return {
        "ready": ready,
        "followups": followups,
        "ready_count": ready.count(),
        "followups_count": followups.count(),
        "all_statuses": MOVABLE_STATUSES,
    }


def queue(request):
    return render(request, "core/queue.html", {"active_nav": "queue", **_queue_context()})


@require_POST
def snooze_followup(request, job_id):
    app = get_object_or_404(Application, job_id=job_id)
    base = app.follow_up_at or timezone.now()
    base = max(base, timezone.now())
    app.follow_up_at = base + timedelta(days=7)
    app.save(update_fields=["follow_up_at"])
    if request.headers.get("HX-Request"):
        return render(request, "core/_queue.html", _queue_context())
    return redirect("queue")
