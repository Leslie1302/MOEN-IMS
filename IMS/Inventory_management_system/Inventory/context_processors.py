from .models import Profile

def user_profile(request):
    """Ensure profile is available globally in templates"""
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return {'profile': profile}
    return {'profile': None}
