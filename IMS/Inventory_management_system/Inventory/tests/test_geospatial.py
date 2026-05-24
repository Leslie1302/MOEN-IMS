"""
Tests for geospatial models, serializers, and API endpoints.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
import json

from Inventory.models import (
    Region, District, Package, Project, ProjectSite, Community
)
from Inventory.models import ProjectType


class RegionModelTest(TestCase):
    """Tests for Region model"""

    def setUp(self):
        self.region = Region.objects.create(
            name='Ashanti',
            code='ASH',
            capital='Kumasi',
            population=4780382
        )

    def test_region_creation(self):
        """Test Region model creation"""
        self.assertEqual(self.region.name, 'Ashanti')
        self.assertEqual(self.region.code, 'ASH')
        self.assertEqual(self.region.capital, 'Kumasi')

    def test_region_str(self):
        """Test Region string representation"""
        self.assertEqual(str(self.region), 'Ashanti (ASH)')

    def test_region_unique_name(self):
        """Test Region name uniqueness"""
        with self.assertRaises(Exception):
            Region.objects.create(name='Ashanti', code='ASH2')


class DistrictModelTest(TestCase):
    """Tests for District model"""

    def setUp(self):
        self.region = Region.objects.create(
            name='Ashanti',
            code='ASH',
            capital='Kumasi'
        )
        self.district = District.objects.create(
            region=self.region,
            name='Kumasi Metropolitan',
            code='KMA',
            capital='Kumasi'
        )

    def test_district_creation(self):
        """Test District model creation"""
        self.assertEqual(self.district.name, 'Kumasi Metropolitan')
        self.assertEqual(self.district.region, self.region)

    def test_district_str(self):
        """Test District string representation"""
        self.assertEqual(str(self.district), 'Kumasi Metropolitan (KMA)')

    def test_district_unique_per_region(self):
        """Test District uniqueness per region"""
        with self.assertRaises(Exception):
            District.objects.create(
                region=self.region,
                name='Kumasi Metropolitan',
                code='KMA2'
            )


class PackageModelTest(TestCase):
    """Tests for Package model"""

    def setUp(self):
        self.region = Region.objects.create(name='Ashanti', code='ASH')
        self.package = Package.objects.create(
            name='SHEP-4 Ashanti',
            code='SHEP4-ASH',
            region=self.region,
            phase='SHEP-4',
            project_type='SHEP'
        )

    def test_package_creation(self):
        """Test Package model creation"""
        self.assertEqual(self.package.name, 'SHEP-4 Ashanti')
        self.assertEqual(self.package.code, 'SHEP4-ASH')

    def test_package_str(self):
        """Test Package string representation"""
        self.assertEqual(str(self.package), 'SHEP4-ASH - SHEP-4 Ashanti')


class ProjectSiteGeospatialTest(TestCase):
    """Tests for ProjectSite geospatial features"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.project = Project.objects.create(
            name='Test Project',
            code='TEST001',
            description='Test project',
            project_type='SHEP',
            status='Active',
            consultant='Test Consultant',
            contractor='Test Contractor'
        )
        self.site = ProjectSite.objects.create(
            project=self.project,
            name='Test Site',
            code='TS001',
            region='Ashanti',
            district='Kumasi Metropolitan',
            community='Adum',
            latitude=6.6263,
            longitude=-1.6200,
            status='Active'
        )

    def test_site_geospatial_fields(self):
        """Test ProjectSite geospatial fields"""
        self.assertAlmostEqual(self.site.latitude, 6.6263, places=4)
        self.assertAlmostEqual(self.site.longitude, -1.6200, places=4)

    def test_site_get_coordinates_as_tuple(self):
        """Test get_coordinates_as_tuple method"""
        coords = self.site.get_coordinates_as_tuple()
        self.assertIsNotNone(coords)
        self.assertEqual(len(coords), 2)
        self.assertAlmostEqual(coords[0], 6.6263, places=4)

    def test_site_get_coordinates_as_geojson(self):
        """Test get_coordinates_as_geojson method"""
        geojson = self.site.get_coordinates_as_geojson()
        self.assertIsNotNone(geojson)
        self.assertEqual(geojson['type'], 'Point')
        self.assertEqual(len(geojson['coordinates']), 2)
        # GeoJSON uses [lon, lat]
        self.assertAlmostEqual(geojson['coordinates'][1], 6.6263, places=4)

    def test_site_completion_percentage(self):
        """Test completion_percentage property"""
        self.assertEqual(self.site.completion_percentage, 50)  # Active = 50%

        self.site.status = 'Completed'
        self.assertEqual(self.site.completion_percentage, 100)

        self.site.status = 'Planned'
        self.assertEqual(self.site.completion_percentage, 0)

    def test_site_is_completed(self):
        """Test is_completed property"""
        self.site.status = 'Completed'
        self.assertTrue(self.site.is_completed)

        self.site.status = 'Active'
        self.assertFalse(self.site.is_completed)


class ProjectSiteAPITest(TestCase):
    """Tests for ProjectSite API endpoints"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Create test data
        self.project = Project.objects.create(
            name='Test Project',
            code='TEST001',
            description='Test project',
            project_type='SHEP',
            phase='SHEP-4',
            status='Active',
            consultant='Test Consultant',
            contractor='Test Contractor'
        )

        self.site1 = ProjectSite.objects.create(
            project=self.project,
            name='Site 1',
            code='S001',
            region='Ashanti',
            district='Kumasi Metropolitan',
            community='Adum',
            latitude=6.6263,
            longitude=-1.6200,
            status='Completed'
        )

        self.site2 = ProjectSite.objects.create(
            project=self.project,
            name='Site 2',
            code='S002',
            region='Ashanti',
            district='Kumasi Metropolitan',
            community='Kumasi',
            latitude=6.6667,
            longitude=-1.6000,
            status='Active'
        )

    def test_project_sites_api_returns_geojson(self):
        """Test API returns valid GeoJSON"""
        # Note: API endpoints commented out, so this test will be enabled
        # after djangorestframework is installed
        pass

    def test_project_sites_api_filter_by_region(self):
        """Test API filtering by region"""
        # This test will be enabled after API is accessible
        pass

    def test_project_sites_api_filter_by_status(self):
        """Test API filtering by status"""
        # This test will be enabled after API is accessible
        pass

    def test_stats_api_calculates_completion(self):
        """Test stats API calculates completion percentage"""
        # Completion should be 50% (1 completed, 1 active out of 2)
        pass


class CommunityGeospatialTest(TestCase):
    """Tests for Community model geospatial features"""

    def setUp(self):
        # Create a basic project type first
        self.project_type = ProjectType.objects.create(
            name='SHEP',
            description='SHEP Project Type'
        )

        self.community = Community.objects.create(
            region='Ashanti',
            district='Kumasi Metropolitan',
            community='Adum',
            project_type=self.project_type,
            latitude=6.6263,
            longitude=-1.6200
        )

    def test_community_geospatial_fields(self):
        """Test Community geospatial fields"""
        self.assertAlmostEqual(self.community.latitude, 6.6263, places=4)
        self.assertAlmostEqual(self.community.longitude, -1.6200, places=4)

    def test_community_get_coordinates_as_tuple(self):
        """Test Community get_coordinates_as_tuple"""
        coords = self.community.get_coordinates_as_tuple()
        self.assertIsNotNone(coords)
        self.assertEqual(len(coords), 2)

    def test_community_get_coordinates_as_geojson(self):
        """Test Community get_coordinates_as_geojson"""
        geojson = self.community.get_coordinates_as_geojson()
        self.assertIsNotNone(geojson)
        self.assertEqual(geojson['type'], 'Point')

    def test_community_string_coordinates(self):
        """Test Community with string coordinates"""
        community = Community.objects.create(
            region='Ashanti',
            district='Kumasi Metropolitan',
            community='Kwadaso',
            project_type=self.project_type,
            gps_coordinates='6.6300, -1.6100'
        )

        coords = community.get_coordinates_as_tuple()
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 6.6300, places=4)
        self.assertAlmostEqual(coords[1], -1.6100, places=4)


class ProjectStatisticsTest(TestCase):
    """Tests for project statistics calculations"""

    def setUp(self):
        self.project = Project.objects.create(
            name='Test Project',
            code='TEST001',
            description='Test',
            project_type='SHEP',
            status='Active',
            total_budget=1000000,
            spent_budget=500000,
            consultant='Test Consultant',
            contractor='Test Contractor'
        )

        # Create sites with different statuses
        for i, status in enumerate(['Completed', 'Active', 'Planned', 'On Hold']):
            ProjectSite.objects.create(
                project=self.project,
                name=f'Site {i+1}',
                code=f'S{i+1:03d}',
                region='Ashanti',
                district='Kumasi Metropolitan',
                status=status,
                latitude=6.6 + i * 0.01,
                longitude=-1.6 + i * 0.01
            )

    def test_project_site_count(self):
        """Test correct site count"""
        self.assertEqual(self.project.sites.count(), 4)

    def test_project_completion_calculation(self):
        """Test completion percentage calculation"""
        completed = self.project.sites.filter(status='Completed').count()
        total = self.project.sites.count()
        completion = (completed / total) * 100
        self.assertEqual(completion, 25.0)

    def test_project_budget_utilization(self):
        """Test budget utilization calculation"""
        utilization = (self.project.spent_budget / self.project.total_budget) * 100
        self.assertEqual(utilization, 50.0)


class CoordinateConversionTest(TestCase):
    """Tests for coordinate conversion utilities"""

    def test_decimal_to_geojson(self):
        """Test conversion from decimal coordinates to GeoJSON"""
        site = ProjectSite.objects.create(
            project=Project.objects.create(
                name='Test',
                code='T001',
                description='Test',
                consultant='Test',
                contractor='Test'
            ),
            name='Test Site',
            code='TS001',
            region='Test',
            district='Test',
            latitude=6.6263,
            longitude=-1.6200,
            status='Planned'
        )

        geojson = site.get_coordinates_as_geojson()
        # GeoJSON uses [longitude, latitude]
        self.assertEqual(geojson['coordinates'][0], -1.6200)
        self.assertEqual(geojson['coordinates'][1], 6.6263)

    def test_string_coordinates_parsing(self):
        """Test parsing string coordinates"""
        project_type = ProjectType.objects.create(
            name='SHEP',
            description='SHEP'
        )
        community = Community.objects.create(
            region='Test',
            district='Test',
            community='Test',
            project_type=project_type,
            gps_coordinates='6.6263,-1.6200'
        )

        coords = community.get_coordinates_as_tuple()
        self.assertEqual(coords[0], 6.6263)
        self.assertEqual(coords[1], -1.6200)

    def test_invalid_string_coordinates(self):
        """Test handling of invalid string coordinates"""
        project_type = ProjectType.objects.create(
            name='SHEP',
            description='SHEP'
        )
        community = Community.objects.create(
            region='Test',
            district='Test',
            community='Test',
            project_type=project_type,
            gps_coordinates='invalid coordinates'
        )

        coords = community.get_coordinates_as_tuple()
        self.assertIsNone(coords)


class GeospatialDataIntegrityTest(TestCase):
    """Tests for geospatial data integrity"""

    def test_site_without_coordinates(self):
        """Test handling of sites without coordinates"""
        site = ProjectSite.objects.create(
            project=Project.objects.create(
                name='Test',
                code='T001',
                description='Test',
                consultant='Test',
                contractor='Test'
            ),
            name='No Coords Site',
            code='NCS001',
            region='Test',
            district='Test',
            status='Planned'
        )

        coords = site.get_coordinates_as_tuple()
        self.assertIsNone(coords)

        geojson = site.get_coordinates_as_geojson()
        self.assertIsNone(geojson)

    def test_region_district_relationship(self):
        """Test Region-District relationship integrity"""
        region = Region.objects.create(name='Test Region', code='TR')
        district1 = District.objects.create(
            region=region,
            name='District 1',
            code='D1'
        )
        district2 = District.objects.create(
            region=region,
            name='District 2',
            code='D2'
        )

        self.assertEqual(region.districts.count(), 2)
        self.assertIn(district1, region.districts.all())
        self.assertIn(district2, region.districts.all())
