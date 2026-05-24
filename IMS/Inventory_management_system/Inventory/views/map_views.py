from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count

from ..models.projects import ProjectSite

@login_required
def ghana_map_view(request):
    """View to render the Ghana Map Representation"""
    return render(request, 'Inventory/ghana_map.html')

@login_required
def ghana_map_data_api(request):
    """
    API endpoint to get regional project site progress data and Access Rate (AR%)
    AR% = (Completed sites / Total sites) * 100 for this project
    """
    # Standard 16 regions of Ghana
    standard_regions = [
        'Upper West', 'Upper East', 'North East', 'Savannah', 'Northern',
        'Oti', 'Bono East', 'Bono', 'Western North', 'Ahafo', 'Ashanti',
        'Eastern', 'Volta', 'Western', 'Central', 'Greater Accra'
    ]

    data = []
    national_totals = {
        'total_sites': 0,
        'completed_sites': 0,
        'active_sites': 0,
        'planned_sites': 0,
        'on_hold_sites': 0,
    }

    for region in standard_regions:
        # We use icontains to match variations like "Greater Accra Region" or "Ashanti Region"
        region_sites = ProjectSite.objects.filter(region__icontains=region)

        total_sites = region_sites.count()
        completed_sites = region_sites.filter(status='Completed').count()
        active_sites = region_sites.filter(status='Active').count()
        planned_sites = region_sites.filter(status='Planned').count()
        on_hold_sites = region_sites.filter(status='On Hold').count()

        # Calculate Access Rate % for this region
        # AR% = (Completed sites / Total sites) * 100
        ar_percentage = round((completed_sites / total_sites) * 100, 2) if total_sites > 0 else 0

        # Accumulate national totals
        national_totals['total_sites'] += total_sites
        national_totals['completed_sites'] += completed_sites
        national_totals['active_sites'] += active_sites
        national_totals['planned_sites'] += planned_sites
        national_totals['on_hold_sites'] += on_hold_sites

        data.append({
            'name': region,
            'value': ar_percentage,  # ECharts uses 'value' for VisualMap scale (AR%)
            'total_sites': total_sites,
            'completed_sites': completed_sites,
            'active_sites': active_sites,
            'planned_sites': planned_sites,
            'on_hold_sites': on_hold_sites,
            'access_rate': ar_percentage,  # Explicit AR% field
        })

    # Calculate national access rate
    national_ar = round(
        (national_totals['completed_sites'] / national_totals['total_sites']) * 100, 2
    ) if national_totals['total_sites'] > 0 else 0

    return JsonResponse({
        'data': data,
        'national': {
            'total_sites': national_totals['total_sites'],
            'completed_sites': national_totals['completed_sites'],
            'active_sites': national_totals['active_sites'],
            'planned_sites': national_totals['planned_sites'],
            'on_hold_sites': national_totals['on_hold_sites'],
            'access_rate': national_ar,  # National AR%
        }
    }, safe=False)
