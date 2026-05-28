from .models import Profile


def sidebar(request):
    return {"sidebar_profile": Profile.objects.first()}
