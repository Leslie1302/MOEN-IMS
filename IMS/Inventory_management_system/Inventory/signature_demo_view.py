"""
View for displaying the digital signature stamp demo page.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Profile


@login_required
def signature_stamp_demo(request):
    """
    Display a demo page showcasing all digital signature stamps.
    Shows all users' stamps with various examples and usage patterns.
    """
    # Get all profiles that have signature stamps
    profiles = Profile.objects.filter(
        signature_stamp__isnull=False,
        user__isnull=False
    ).select_related('user')
    
    context = {
        'profiles': profiles,
    }
    
    return render(request, 'Inventory/signature_demo.html', context)
