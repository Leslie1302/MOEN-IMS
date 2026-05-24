"""
Geospatial API views for Ghana Map project tracking system.
Provides GeoJSON endpoints for displaying projects, sites, and statistics on interactive maps.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum
from django.utils.timezone import now
from datetime import timedelta

from Inventory.models import ProjectSite, Project, Region, District, Community, Package
from Inventory.serializers import (
    ProjectSiteGeoJSONSerializer,
    RegionHeatmapSerializer,
    CommunitySerializer,
)


@require_http_methods(["GET"])
def ghana_map_project_sites_api(request):
    """
    API endpoint: GET /api/ghana-map-project-sites/

    Returns all project sites as GeoJSON FeatureCollection, with optional filtering.

    Query Parameters:
    - project_type: comma-separated list (SHEP, Turnkey, China Water, etc.)
    - phase: SHEP phase (e.g., SHEP-4)
    - region: region name
    - district: district name
    - community: community name
    - status: project status (Planning, Active, Completed, On Hold, Cancelled)
    - site_status: site status (Planned, Active, Completed, On Hold)
    - start_date: ISO format date (2024-01-01)
    - end_date: ISO format date

    Returns: GeoJSON FeatureCollection
    """
    try:
        # Start with all project sites
        queryset = ProjectSite.objects.select_related('project', 'site_supervisor').all()

        # Apply filters based on query parameters
        project_types = request.GET.getlist('project_type')
        if project_types:
            queryset = queryset.filter(project__project_type__in=project_types)

        phase = request.GET.get('phase')
        if phase:
            queryset = queryset.filter(project__phase=phase)

        region = request.GET.get('region')
        if region:
            queryset = queryset.filter(region=region)

        district = request.GET.get('district')
        if district:
            queryset = queryset.filter(district=district)

        community = request.GET.get('community')
        if community:
            queryset = queryset.filter(community=community)

        project_status = request.GET.getlist('status')
        if project_status:
            queryset = queryset.filter(project__status__in=project_status)

        site_status = request.GET.getlist('site_status')
        if site_status:
            queryset = queryset.filter(status__in=site_status)

        start_date = request.GET.get('start_date')
        if start_date:
            queryset = queryset.filter(project__start_date__gte=start_date)

        end_date = request.GET.get('end_date')
        if end_date:
            queryset = queryset.filter(project__planned_end_date__lte=end_date)

        # Serialize to GeoJSON
        sites = queryset.order_by('-created_at')[:10000]  # Limit to 10k for performance
        serializer = ProjectSiteGeoJSONSerializer(sites, many=True)

        # Build GeoJSON FeatureCollection
        geojson = {
            'type': 'FeatureCollection',
            'features': serializer.data,
            'meta': {
                'count': queryset.count(),
                'timestamp': now().isoformat(),
            }
        }

        return JsonResponse(geojson, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def ghana_map_region_heatmap_api(request):
    """
    API endpoint: GET /api/ghana-map-region-heatmap/

    Returns Ghana's regions with aggregated project statistics for heatmap visualization.
    Color regions based on completion percentage.

    Query Parameters:
    - project_type: filter by project type
    - phase: filter by phase
    - include_empty: include regions with no projects (default: true)

    Returns: GeoJSON FeatureCollection with region boundaries
    """
    try:
        include_empty = request.GET.get('include_empty', 'true').lower() == 'true'

        # Get all regions
        regions = Region.objects.all()

        # Apply optional filters to calculate statistics
        project_types = request.GET.getlist('project_type')
        phase = request.GET.get('phase')

        features = []
        for region in regions:
            # Get sites in this region
            sites_queryset = ProjectSite.objects.filter(region=region.name)

            # Apply filters
            if project_types:
                sites_queryset = sites_queryset.filter(project__project_type__in=project_types)
            if phase:
                sites_queryset = sites_queryset.filter(project__phase=phase)

            # Skip empty regions if requested
            if not include_empty and sites_queryset.count() == 0:
                continue

            # Calculate statistics
            total_sites = sites_queryset.count()
            completed_sites = sites_queryset.filter(status='Completed').count()
            active_sites = sites_queryset.filter(status='Active').count()
            planned_sites = sites_queryset.filter(status='Planned').count()

            completion_rate = (completed_sites / total_sites * 100) if total_sites > 0 else 0

            # Determine heatmap color
            if completion_rate >= 80:
                color = '#00AA00'  # Dark green
            elif completion_rate >= 60:
                color = '#AAAA00'  # Yellow-green
            elif completion_rate >= 40:
                color = '#FFAA00'  # Orange
            elif completion_rate >= 20:
                color = '#FF6600'  # Red-orange
            else:
                color = '#FF0000'  # Red

            feature = {
                'type': 'Feature',
                'properties': {
                    'id': region.id,
                    'name': region.name,
                    'code': region.code,
                    'capital': region.capital,
                    'population': region.population,
                    'total_sites': total_sites,
                    'completed_sites': completed_sites,
                    'active_sites': active_sites,
                    'planned_sites': planned_sites,
                    'completion_rate': round(completion_rate, 2),
                    'heatmap_color': color,
                    'district_count': region.districts.count(),
                },
                'geometry': region.geom_json if region.geom_json else None,
            }
            features.append(feature)

        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'meta': {
                'regions_count': len(features),
                'timestamp': now().isoformat(),
            }
        }

        return JsonResponse(geojson, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def ghana_map_stats_api(request):
    """
    API endpoint: GET /api/ghana-map-stats/

    Returns aggregated project and site statistics with optional filtering.

    Query Parameters: Same as ghana_map_project_sites_api

    Returns: JSON object with statistics
    """
    try:
        # Start with all sites
        queryset = ProjectSite.objects.select_related('project').all()

        # Apply filters
        project_types = request.GET.getlist('project_type')
        if project_types:
            queryset = queryset.filter(project__project_type__in=project_types)

        phase = request.GET.get('phase')
        if phase:
            queryset = queryset.filter(project__phase=phase)

        region = request.GET.get('region')
        if region:
            queryset = queryset.filter(region=region)

        district = request.GET.get('district')
        if district:
            queryset = queryset.filter(district=district)

        project_status = request.GET.getlist('status')
        if project_status:
            queryset = queryset.filter(project__status__in=project_status)

        site_status = request.GET.getlist('site_status')
        if site_status:
            queryset = queryset.filter(status__in=site_status)

        # Calculate statistics
        total_sites = queryset.count()
        completed_sites = queryset.filter(status='Completed').count()
        active_sites = queryset.filter(status='Active').count()
        planned_sites = queryset.filter(status='Planned').count()
        on_hold_sites = queryset.filter(status='On Hold').count()

        # Project statistics
        projects_queryset = Project.objects.all()
        if project_types:
            projects_queryset = projects_queryset.filter(project_type__in=project_types)
        if phase:
            projects_queryset = projects_queryset.filter(phase=phase)
        if project_status:
            projects_queryset = projects_queryset.filter(status__in=project_status)

        total_projects = projects_queryset.count()
        active_projects = projects_queryset.filter(status='Active').count()
        completed_projects = projects_queryset.filter(status='Completed').count()
        planned_projects = projects_queryset.filter(status='Planning').count()

        # Calculate completion percentage
        completion_percentage = (completed_sites / total_sites * 100) if total_sites > 0 else 0

        # Budget statistics
        total_budget = projects_queryset.aggregate(Sum('total_budget'))['total_budget__sum'] or 0
        spent_budget = projects_queryset.aggregate(Sum('spent_budget'))['spent_budget__sum'] or 0
        budget_utilization = (spent_budget / total_budget * 100) if total_budget > 0 else 0

        # Overdue sites (past planned completion date)
        today = now().date()
        overdue_sites = queryset.filter(
            planned_completion_date__lt=today,
            status__in=['Planned', 'Active']
        ).count()

        # At-risk sites (within 30 days of completion)
        at_risk_date = today + timedelta(days=30)
        at_risk_sites = queryset.filter(
            planned_completion_date__lte=at_risk_date,
            planned_completion_date__gt=today,
            status='Active'
        ).count()

        # Completion by status
        completion_by_status = {
            'Completed': completed_sites,
            'Active': active_sites,
            'Planned': planned_sites,
            'On Hold': on_hold_sites,
        }

        # Completion by region
        completion_by_region = {}
        for region_name in queryset.values_list('region', flat=True).distinct():
            region_sites = queryset.filter(region=region_name)
            region_completed = region_sites.filter(status='Completed').count()
            region_total = region_sites.count()
            completion_by_region[region_name] = {
                'total': region_total,
                'completed': region_completed,
                'percentage': (region_completed / region_total * 100) if region_total > 0 else 0
            }

        stats = {
            'projects': {
                'total': total_projects,
                'active': active_projects,
                'completed': completed_projects,
                'planned': planned_projects,
            },
            'sites': {
                'total': total_sites,
                'active': active_sites,
                'completed': completed_sites,
                'planned': planned_sites,
                'on_hold': on_hold_sites,
                'overdue': overdue_sites,
                'at_risk': at_risk_sites,
            },
            'completion': {
                'percentage': round(completion_percentage, 2),
                'by_status': completion_by_status,
                'by_region': completion_by_region,
            },
            'budget': {
                'total': float(total_budget),
                'spent': float(spent_budget),
                'utilization_percentage': round(budget_utilization, 2),
            },
            'timestamp': now().isoformat(),
        }

        return JsonResponse(stats, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def ghana_map_districts_api(request):
    """
    API endpoint: GET /api/ghana-map-districts/

    Returns districts for a given region (used for cascading dropdowns).

    Query Parameters:
    - region: Region name (required)
    - include_stats: Include site count and completion stats (true/false, default: true)

    Returns: JSON array of districts
    """
    try:
        region_name = request.GET.get('region')
        if not region_name:
            return JsonResponse({'error': 'region parameter is required'}, status=400)

        include_stats = request.GET.get('include_stats', 'true').lower() == 'true'

        try:
            region = Region.objects.get(name=region_name)
        except Region.DoesNotExist:
            return JsonResponse({'error': f'Region "{region_name}" not found'}, status=404)

        districts = region.districts.all()
        districts_data = []

        for district in districts:
            data = {
                'id': district.id,
                'name': district.name,
                'code': district.code,
                'capital': district.capital,
                'population': district.population,
            }

            if include_stats:
                sites = ProjectSite.objects.filter(
                    region=region_name,
                    district=district.name
                )
                data['site_count'] = sites.count()
                data['completed_sites'] = sites.filter(status='Completed').count()
                data['completion_percentage'] = (
                    data['completed_sites'] / data['site_count'] * 100
                    if data['site_count'] > 0 else 0
                )

            districts_data.append(data)

        return JsonResponse({
            'region': region_name,
            'districts': districts_data,
            'count': len(districts_data),
            'timestamp': now().isoformat(),
        }, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def ghana_map_communities_api(request):
    """
    API endpoint: GET /api/ghana-map-communities/

    Returns communities for a given district with geospatial data.

    Query Parameters:
    - district: District name (required)
    - region: Region name (optional, for validation)

    Returns: GeoJSON FeatureCollection of communities
    """
    try:
        district_name = request.GET.get('district')
        region_name = request.GET.get('region')

        if not district_name:
            return JsonResponse({'error': 'district parameter is required'}, status=400)

        try:
            if region_name:
                district = District.objects.get(name=district_name, region__name=region_name)
            else:
                district = District.objects.get(name=district_name)
        except District.DoesNotExist:
            return JsonResponse({'error': f'District "{district_name}" not found'}, status=404)

        communities = district.communities.all()
        serializer = CommunitySerializer(communities, many=True)

        features = []
        for community in communities:
            geojson = community.get_coordinates_as_geojson()
            if geojson:
                feature = {
                    'type': 'Feature',
                    'geometry': geojson,
                    'properties': {
                        'id': community.id,
                        'name': community.name,
                        'code': community.code,
                        'district': community.district.name,
                        'region': community.region.name,
                        'population': community.population,
                        'chieftain': community.chieftain,
                        'total_projects': community.total_projects,
                        'completed_projects': community.completed_projects,
                    }
                }
                features.append(feature)

        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'meta': {
                'district': district_name,
                'region': region_name,
                'count': len(features),
                'timestamp': now().isoformat(),
            }
        }

        return JsonResponse(geojson, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
