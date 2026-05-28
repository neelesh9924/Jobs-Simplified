from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("htmx-ping/", views.htmx_ping, name="htmx_ping"),
    path("profile/", views.profile_view, name="profile"),
    path("jobs/", views.job_list, name="job_list"),
    path("jobs/add/", views.add_job, name="add_job"),
    path("jobs/fragment/", views.job_list_fragment, name="job_list_fragment"),
    path("jobs/<int:job_id>/", views.job_detail, name="job_detail"),
    path("jobs/<int:job_id>/tailor/", views.tailor_job, name="tailor_job"),
    path("resume-version/<int:version_id>/pdf/", views.resume_pdf, name="resume_pdf"),
    path("resume/base.pdf", views.base_resume_pdf, name="base_resume_pdf"),
    # LaTeX editor (kind = "base" | "version")
    path("editor/<str:kind>/<int:pk>/", views.editor, name="editor"),
    path("editor/<str:kind>/<int:pk>/preview/", views.editor_preview, name="editor_preview"),
    path("editor/<str:kind>/<int:pk>/compile/", views.editor_compile, name="editor_compile"),
    # Tracker / pipeline
    path("tracker/", views.tracker, name="tracker"),
    path("tracker/fragment/", views.tracker_fragment, name="tracker_fragment"),
    path("jobs/<int:job_id>/status/", views.set_status, name="set_status"),
    # Review queue + follow-ups
    path("queue/", views.queue, name="queue"),
    path("queue/fragment/", views.queue_fragment, name="queue_fragment"),
    path("jobs/<int:job_id>/snooze/", views.snooze_followup, name="snooze_followup"),
    # Scraper / ingestion observability
    path("ingestion/", views.ingestion, name="ingestion"),
    path("ingestion/fragment/", views.ingestion_fragment, name="ingestion_fragment"),
    path("ingestion/run/", views.run_ingest, name="run_ingest"),
    # Filter presets
    path("presets/save/", views.save_preset, name="save_preset"),
    path("presets/<int:preset_id>/delete/", views.delete_preset, name="delete_preset"),
]
