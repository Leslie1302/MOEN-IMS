"""
Serializers for geospatial API endpoints.
Converts Django models to GeoJSON and other geospatial formats.
"""

from rest_framework import serializers
from Inventory.models import ProjectSite, Project, Region, District, Community, Package


class ProjectSiteGeoJSONSerializer(serializers.ModelSerializer):
    """
    Serializes ProjectSite instances to GeoJSON Feature format.
    Used by the Ghana Map API to display project sites on the map.
    """
    # GeoJSON fields
    type = serializers.SerializerMethodField()
    geometry = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()

    class Meta:
        model = ProjectSite
        fields = ['type', 'geometry', 'properties', 'id']

    def get_type(self, obj):
        return 'Feature'

    def get_geometry(self, obj):
        """Return geometry as GeoJSON point"""
        coords = obj.get_coordinates_as_geojson()
        if coords:
            return coords
        # If no coordinates, return a null geometry
        return None

    def get_properties(self, obj):
        """Return site properties for the GeoJSON feature"""
        return {
            'id': obj.id,
            'name': obj.name,
            'code': obj.code,
            'community': obj.community,
            'region': obj.region,
            'district': obj.district,
            'status': obj.status,
            'status_color': self._get_status_color(obj.status),
            'completion_percentage': obj.completion_percentage,
            'project_code': obj.project.code,
            'project_name': obj.project.name,
            'project_type': obj.project.project_type,
            'phase': obj.project.phase,
            'supervisor': obj.site_supervisor.get_full_name() if obj.site_supervisor else 'Unassigned',
            'start_date': obj.start_date.isoformat() if obj.start_date else None,
            'planned_completion': obj.planned_completion_date.isoformat() if obj.planned_completion_date else None,
            'actual_completion': obj.actual_completion_date.isoformat() if obj.actual_completion_date else None,
            'created_at': obj.created_at.isoformat(),
            'updated_at': obj.updated_at.isoformat(),
        }

    @staticmethod
    def _get_status_color(status):
        """Return color code for status"""
        colors = {
            'Planned': '#808080',      # Gray
            'Active': '#FFA500',       # Orange
            'Completed': '#00AA00',    # Green
            'On Hold': '#FF6666',      # Red
        }
        return colors.get(status, '#808080')


class RegionHeatmapSerializer(serializers.ModelSerializer):
    """
    Serializes Region instances with aggregated statistics for heatmap visualization.
    """
    properties = serializers.SerializerMethodField()
    geometry = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'code', 'geometry', 'properties']

    def get_geometry(self, obj):
        """Return geometry from GeoJSON"""
        if obj.geom_json:
            return obj.geom_json
        return None

    def get_properties(self, obj):
        """Return aggregated region statistics"""
        # Get all sites in this region
        sites = ProjectSite.objects.filter(region=obj.name)

        # Calculate statistics
        total_sites = sites.count()
        completed_sites = sites.filter(status='Completed').count()
        active_sites = sites.filter(status='Active').count()
        planned_sites = sites.filter(status='Planned').count()

        completion_rate = (completed_sites / total_sites * 100) if total_sites > 0 else 0

        return {
            'id': obj.id,
            'name': obj.name,
            'code': obj.code,
            'capital': obj.capital,
            'population': obj.population,
            'total_sites': total_sites,
            'completed_sites': completed_sites,
            'active_sites': active_sites,
            'planned_sites': planned_sites,
            'completion_rate': round(completion_rate, 2),
            'heatmap_color': self._get_heatmap_color(completion_rate),
            'district_count': obj.districts.count(),
            'community_count': obj.communities.count(),
        }

    @staticmethod
    def _get_heatmap_color(completion_rate):
        """Return color based on completion percentage"""
        if completion_rate >= 80:
            return '#00AA00'  # Dark green
        elif completion_rate >= 60:
            return '#AAAA00'  # Yellow-green
        elif completion_rate >= 40:
            return '#FFAA00'  # Orange
        elif completion_rate >= 20:
            return '#FF6600'  # Red-orange
        else:
            return '#FF0000'  # Red


class DistrictSerializer(serializers.ModelSerializer):
    """
    Basic serializer for District model.
    Used for cascading dropdowns in forms.
    """
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = District
        fields = ['id', 'name', 'code', 'region', 'region_name', 'capital', 'population']


class CommunitySerializer(serializers.ModelSerializer):
    """
    Serializer for Community model with geospatial data.
    """
    district_name = serializers.CharField(source='district.name', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    geojson = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            'id', 'name', 'code', 'region', 'region_name',
            'district', 'district_name', 'latitude', 'longitude',
            'gps_coordinates', 'geojson', 'population', 'chieftain'
        ]

    def get_geojson(self, obj):
        """Return community as GeoJSON point"""
        return obj.get_coordinates_as_geojson()


class ProjectStatisticsSerializer(serializers.Serializer):
    """
    Serializer for project statistics across filters.
    Used by the ghana_map_stats_api endpoint.
    """
    total_projects = serializers.IntegerField()
    active_projects = serializers.IntegerField()
    completed_projects = serializers.IntegerField()
    planned_projects = serializers.IntegerField()

    total_sites = serializers.IntegerField()
    active_sites = serializers.IntegerField()
    completed_sites = serializers.IntegerField()
    planned_sites = serializers.IntegerField()

    completion_percentage = serializers.FloatField()
    completion_by_status = serializers.DictField()
    completion_by_region = serializers.DictField()
    completion_by_district = serializers.DictField()

    # Budget statistics
    total_budget = serializers.DecimalField(max_digits=15, decimal_places=2)
    spent_budget = serializers.DecimalField(max_digits=15, decimal_places=2)
    budget_utilization = serializers.FloatField()

    # Timeline statistics
    overdue_sites = serializers.IntegerField()
    at_risk_sites = serializers.IntegerField()


class GhanaMapFiltersSerializer(serializers.Serializer):
    """
    Serializer for validating and documenting Ghana Map filter parameters.
    """
    project_type = serializers.MultipleChoiceField(
        choices=['SHEP', 'Turnkey', 'China Water', 'Other Electrification'],
        required=False,
        help_text="Filter by project type (comma-separated or multiple selections)"
    )
    phase = serializers.CharField(
        required=False,
        help_text="Filter by project phase (e.g., SHEP-4)"
    )
    region = serializers.CharField(
        required=False,
        help_text="Filter by region name"
    )
    district = serializers.CharField(
        required=False,
        help_text="Filter by district name"
    )
    community = serializers.CharField(
        required=False,
        help_text="Filter by community name"
    )
    status = serializers.MultipleChoiceField(
        choices=['Planning', 'Active', 'On Hold', 'Completed', 'Cancelled'],
        required=False,
        help_text="Filter by project status"
    )
    site_status = serializers.MultipleChoiceField(
        choices=['Planned', 'Active', 'Completed', 'On Hold'],
        required=False,
        help_text="Filter by project site status"
    )
    start_date = serializers.DateField(
        required=False,
        help_text="Filter projects starting after this date"
    )
    end_date = serializers.DateField(
        required=False,
        help_text="Filter projects ending before this date"
    )
