from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("htmx-ping/", views.htmx_ping, name="htmx_ping"),
    path("jobs/", views.job_list, name="job_list"),
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
    path("jobs/<int:job_id>/status/", views.set_status, name="set_status"),
    # Review queue + follow-ups
    path("queue/", views.queue, name="queue"),
    path("jobs/<int:job_id>/snooze/", views.snooze_followup, name="snooze_followup"),
    # Filter presets
    path("presets/save/", views.save_preset, name="save_preset"),
    path("presets/<int:preset_id>/delete/", views.delete_preset, name="delete_preset"),
]
