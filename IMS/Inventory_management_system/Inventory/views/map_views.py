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
    """API endpoint to get regional project site progress data"""
    # Standard 16 regions of Ghana
    standard_regions = [
        'Upper West', 'Upper East', 'North East', 'Savannah', 'Northern',
        'Oti', 'Bono East', 'Bono', 'Western North', 'Ahafo', 'Ashanti',
        'Eastern', 'Volta', 'Western', 'Central', 'Greater Accra'
    ]
    
    data = []
    
    for region in standard_regions:
        # We use icontains to match variations like "Greater Accra Region" or "Ashanti Region"
        region_sites = ProjectSite.objects.filter(region__icontains=region)
        
        total_sites = region_sites.count()
        completed_sites = region_sites.filter(status='Completed').count()
        active_sites = region_sites.filter(status='Active').count()
        planned_sites = region_sites.filter(status='Planned').count()
        on_hold_sites = region_sites.filter(status='On Hold').count()
        
        if total_sites > 0:
            progress_percentage = round((completed_sites / total_sites) * 100, 2)
        else:
            progress_percentage = 0
            
        data.append({
            'name': region,
            'value': progress_percentage, # ECharts uses 'value' for VisualMap scale
            'total_sites': total_sites,
            'completed_sites': completed_sites,
            'active_sites': active_sites,
            'planned_sites': planned_sites,
            'on_hold_sites': on_hold_sites,
        })
        
    return JsonResponse({'data': data}, safe=False)
