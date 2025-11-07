"""
View for digital signature lookup and verification.
Allows searching and viewing signatures by user ID, username, or signature ID.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Count
from .models import Profile


@login_required
def signature_lookup(request):
    """
    Display a searchable list of all digital signatures.
    Supports searching by username, email, or signature ID.
    """
    # Get search parameters
    search_query = request.GET.get('q', '').strip()
    signature_id = request.GET.get('sig_id', '').strip()
    
    # Start with all profiles that have signatures
    profiles = Profile.objects.filter(
        signature_stamp__isnull=False,
        user__isnull=False
    ).select_related('user')
    
    # Apply search filters
    if search_query:
        profiles = profiles.filter(
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    if signature_id:
        profiles = profiles.filter(
            signature_stamp__icontains=signature_id
        )
    
    # Order by username
    profiles = profiles.order_by('user__username')
    
    # Calculate statistics
    total_users = User.objects.count()
    users_with_signatures = Profile.objects.filter(
        signature_stamp__isnull=False
    ).count()
    active_users = User.objects.filter(is_active=True).count()
    staff_users = User.objects.filter(is_staff=True).count()
    
    context = {
        'profiles': profiles,
        'search_query': search_query,
        'signature_id': signature_id,
        'total_users': total_users,
        'users_with_signatures': users_with_signatures,
        'active_users': active_users,
        'staff_users': staff_users,
    }
    
    return render(request, 'Inventory/signature_lookup.html', context)


@login_required
def signature_verify(request, user_id):
    """
    Verify a specific user's signature by user ID.
    Returns detailed information about the signature.
    """
    try:
        profile = Profile.objects.select_related('user').get(user__id=user_id)
        
        # Parse signature data
        stamp_data = profile.display_signature_stamp() if profile.signature_stamp else None
        
        # Check if signature is valid
        is_valid = bool(profile.signature_stamp and stamp_data)
        
        context = {
            'profile': profile,
            'stamp_data': stamp_data,
            'is_valid': is_valid,
        }
        
        return render(request, 'Inventory/signature_verify.html', context)
        
    except Profile.DoesNotExist:
        context = {
            'error': 'User profile not found',
            'user_id': user_id,
        }
        return render(request, 'Inventory/signature_verify.html', context)


@login_required
def signature_api_lookup(request):
    """
    API endpoint for signature lookup.
    Returns JSON data for AJAX requests.
    """
    from django.http import JsonResponse
    
    search_query = request.GET.get('q', '').strip()
    
    if not search_query:
        return JsonResponse({'error': 'No search query provided'}, status=400)
    
    # Search for profiles
    profiles = Profile.objects.filter(
        signature_stamp__isnull=False,
        user__isnull=False
    ).filter(
        Q(user__username__icontains=search_query) |
        Q(user__email__icontains=search_query) |
        Q(signature_stamp__icontains=search_query)
    ).select_related('user')[:10]  # Limit to 10 results
    
    # Build response data
    results = []
    for profile in profiles:
        stamp_data = profile.display_signature_stamp()
        results.append({
            'user_id': profile.user.id,
            'username': profile.user.username,
            'email': profile.user.email,
            'full_name': profile.user.get_full_name(),
            'is_active': profile.user.is_active,
            'is_staff': profile.user.is_staff,
            'signature_stamp': profile.signature_stamp,
            'stamp_data': stamp_data,
        })
    
    return JsonResponse({
        'count': len(results),
        'results': results
    })
