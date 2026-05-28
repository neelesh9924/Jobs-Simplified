from django.contrib import admin
from .models import Profile, Job, Application, ResumeVersion, FilterPreset, IngestRun


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "skill_count", "updated_at")
    readonly_fields = ("updated_at",)

    def skill_count(self, obj):
        return len(obj.skills) if isinstance(obj.skills, list) else 0
    skill_count.short_description = "Skills"


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "source_key", "location", "region", "score", "is_gone", "posted_at")
    list_filter = ("source_key", "is_gone", "region")
    search_fields = ("title", "company", "location")
    readonly_fields = ("created_at", "updated_at", "last_seen_at")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "status", "applied_at", "follow_up_at", "updated_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ResumeVersion)
class ResumeVersionAdmin(admin.ModelAdmin):
    list_display = ("label", "profile", "job", "provider", "created_at")
    readonly_fields = ("created_at",)


@admin.register(FilterPreset)
class FilterPresetAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IngestRun)
class IngestRunAdmin(admin.ModelAdmin):
    list_display = ("source_key", "started_at", "finished_at", "fetched_count", "new_count", "updated_count", "error_count")
    readonly_fields = ("started_at", "finished_at", "fetched_count", "new_count", "updated_count", "error_count", "error_log")
