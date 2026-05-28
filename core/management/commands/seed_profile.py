import re

from django.core.management.base import BaseCommand

from core.models import Profile

RESUME = {
    "name": "Neelesh Singh",
    "title": "Software Engineer -- Android / Flutter",
    "contact": {
        "email": "neelesh9924@gmail.com",
        "phone": "+91 6307664553",
        "github": "https://github.com/neelesh9924",
        "linkedin": "https://www.linkedin.com/in/neelesh9924",
    },
    "summary": (
        "Software Engineer with 2.5+ years of experience owning end-to-end development "
        "of production Android and Flutter applications. Deep experience in offline-first "
        "architectures, background execution, and hardware-integrated workflows powering "
        "payments, POS/ticketing, and fleet operations. Known for building resilient, "
        "high-performance apps used in high-dependency environments."
    ),
    "skill_groups": [
        {"label": "Languages", "items": "Kotlin, Java, Dart, JavaScript"},
        {"label": "Android", "items": "Jetpack Compose, MVVM, ViewModel, WorkManager, Foreground Services, Services, Media APIs, Maps SDK"},
        {"label": "Flutter", "items": "Flutter (Mobile + Web), BLoC, MethodChannels, platform interop"},
        {"label": "Payments & Hardware", "items": "POS machines, ticketing systems, printers/receipts, wallet flows"},
        {"label": "Media & ML", "items": "Audio recording pipelines, segmentation, on-device transcription (Whisper)"},
        {"label": "Cloud & Tools", "items": "Git, CI/CD, Android Studio, VS Code, Figma; AWS (S3, CloudFront, EC2), GCP (Compute, Storage, Firestore), Azure (Blob, Front Door/CDN, VMs)"},
    ],
    "experience": [
        {
            "company": "ApniBus",
            "location": "Gurugram, India",
            "roles": [
                {
                    "title": "Software Development Engineer II",
                    "dates": "Nov 2024 -- Present",
                    "bullets": [
                        "Leading architecture and delivery of frontend systems across 9 production mobile and web applications, owning features end-to-end from build to release.",
                        "Built long-running background pipelines using WorkManager and Foreground Services for lifecycle-safe execution under Android constraints.",
                        "Designed and maintained offline-first workflows with connectivity-aware execution and retry-driven reliability in real-world field conditions.",
                        "Implemented payments, POS workflows, and ticket printing integrated with hardware devices and system services.",
                        "Developed and optimized fleet tracking features including live GPS polling, smooth marker propagation, and route playback.",
                        "Built platform-channel bridges enabling Flutter apps to leverage native Android capabilities (maps, device workflows, performance-critical modules).",
                    ],
                },
                {
                    "title": "Software Development Engineer I",
                    "dates": "Aug 2023 -- Oct 2024",
                    "bullets": [
                        "Shipped and scaled multiple Android (Java/Kotlin) and Flutter applications, improving engagement by 30%.",
                        "Migrated a large-scale business app from native Android (Java) to Flutter, reducing maintenance overhead and accelerating iteration.",
                        "Built internal Flutter dashboards supporting ~250 daily active users.",
                        "Implemented offline-first architecture and connectivity tracking, reducing network-related failures by 95%.",
                    ],
                },
            ],
        },
        {
            "company": "Freelance Android Developer",
            "location": "Remote",
            "roles": [
                {
                    "title": "",
                    "dates": "Jan 2022 -- Aug 2023",
                    "bullets": [
                        "Led end-to-end Android development for TelePrac (DAU 50+), coordinating a small development team.",
                        "Delivered healthcare and school management apps with offline support, notifications, and admin workflows (200+ users).",
                    ],
                },
            ],
        },
    ],
    "products": {
        "frontend_ownership": (
            "Fleet Management App (Flutter), Commuter Booking App (Android Java), "
            "Commuter Booking Website (HTML/JS), Bus Card App (Flutter + Web), "
            "Bus Agent App (Kotlin Compose), CRM Dashboard (Flutter), BD App (Flutter), "
            "Booth App (Kotlin Compose), Data Analytics Dashboard (HTML/JS)."
        ),
        "complex_domains": (
            "Ticketing + POS workflows, printer integrations, offline-first sync, "
            "fleet GPS tracking and playback, platform-channel bridges (Flutter <-> native), "
            "audio recording and transcription pipelines (Whisper)."
        ),
    },
    "projects": [
        {
            "name": "Pandaal -- Event Hosting Platform",
            "bullets": [
                "Built an Android app (Kotlin) and web platform managing events with 2,000+ attendees per event.",
            ],
        },
        {
            "name": "Stackeddd -- Android UI Library",
            "bullets": [
                "Developed a Java-based UI library for dynamic stacked bottom sheets with smooth animations; published via JitPack.",
            ],
        },
    ],
    "education": [
        {
            "degree": "B.Tech in Computer Science Engineering",
            "institution": "Noida Institute of Engineering & Technology, Greater Noida",
            "dates": "2019 -- 2023",
        },
    ],
}

# Flat skill tokens for the keyword scorer (Phase 2).
SKILLS = [
    "Android", "Kotlin", "Java", "Dart", "JavaScript", "Flutter", "Jetpack Compose",
    "MVVM", "ViewModel", "WorkManager", "Foreground Services", "Media APIs", "Maps SDK",
    "BLoC", "MethodChannels", "platform interop", "POS", "ticketing", "printers",
    "wallet", "payments", "fleet tracking", "GPS", "offline-first", "Whisper",
    "transcription", "audio", "Git", "CI/CD", "Android Studio", "Figma",
    "AWS", "GCP", "Firestore", "Azure", "mobile",
]

PREFS = {
    "regions": ["remote", "india", "us"],
    "keywords": ["android", "kotlin", "flutter", "mobile", "jetpack", "compose", "dart", "pos", "sdk"],
    "salary_floor": 0,
}


class Command(BaseCommand):
    help = "Seed (or reset) the single Profile with the real structured resume."

    def handle(self, *args, **options):
        profile = Profile.objects.first()
        if profile is None:
            profile = Profile()
        profile.structured_resume = RESUME
        profile.skills = SKILLS
        profile.prefs = PREFS
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"Seeded profile #{profile.pk} ({RESUME['name']})."))
