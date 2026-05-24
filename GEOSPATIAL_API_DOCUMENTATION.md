# Ghana Map Geospatial Tracking System - API Documentation

**Version**: 1.0  
**Last Updated**: May 18, 2026  
**Status**: Production Ready

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [Getting Started](#getting-started)
4. [User Guide](#user-guide)
5. [Admin Guide](#admin-guide)
6. [Deployment](#deployment)
7. [Troubleshooting](#troubleshooting)

---

## Overview

The Ghana Map Geospatial Tracking System provides real-time visualization and tracking of project implementation across Ghana's 16 administrative regions. The system uses interactive maps with filtering, statistics, and heatmap visualizations to monitor project progress.

### Features

- ✅ **Interactive Map**: Leaflet.js-based map with real-time project site markers
- ✅ **Multi-level Filtering**: Filter by region, district, community, status, type, and phase
- ✅ **Heatmap Visualization**: Color-coded regions showing completion rates
- ✅ **Live Statistics**: Real-time project and site count aggregation
- ✅ **GeoJSON API**: RESTful API endpoints for integration with other systems
- ✅ **Responsive Design**: Mobile, tablet, and desktop compatible
- ✅ **Performance Optimized**: Handles 10,000+ sites efficiently

### Technology Stack

- **Backend**: Django 5.1, Python 3.14
- **Frontend**: Leaflet.js, Bootstrap 5
- **Database**: SQLite (development), PostgreSQL+PostGIS (production-ready)
- **API**: Django REST Framework
- **Maps**: OpenStreetMap tiles (free, no API key required)

---

## API Endpoints

All endpoints return GeoJSON format unless otherwise specified.

### 1. Project Sites (`/api/ghana-map-project-sites/`)

Returns all project sites as GeoJSON FeatureCollection with optional filtering.

**Method**: `GET`

**Query Parameters**:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `project_type` | string (comma-separated) | Filter by project type | `SHEP,Turnkey` |
| `phase` | string | Filter by phase | `SHEP-4` |
| `region` | string | Filter by region name | `Ashanti` |
| `district` | string | Filter by district name | `Kumasi Metropolitan` |
| `community` | string | Filter by community name | `Adum` |
| `status` | string (comma-separated) | Filter by project status | `Active,Completed` |
| `site_status` | string (comma-separated) | Filter by site status | `Active,Completed` |
| `start_date` | ISO date | Filter projects after date | `2024-01-01` |
| `end_date` | ISO date | Filter projects before date | `2024-12-31` |

**Response**:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-1.6200, 6.6263]
      },
      "properties": {
        "id": 1,
        "name": "Site Name",
        "code": "SITE001",
        "community": "Adum",
        "region": "Ashanti",
        "district": "Kumasi Metropolitan",
        "status": "Active",
        "status_color": "#FFA500",
        "completion_percentage": 50,
        "project_code": "SHEP4-ASH",
        "project_name": "SHEP Phase 4 Ashanti",
        "project_type": "SHEP",
        "phase": "SHEP-4",
        "supervisor": "John Doe",
        "start_date": "2024-01-15",
        "planned_completion": "2024-12-31",
        "actual_completion": null,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-05-18T12:00:00Z"
      }
    }
  ],
  "meta": {
    "count": 150,
    "timestamp": "2026-05-18T12:51:00Z"
  }
}
```

**Status Color Codes**:
- `#00aa00` (Green) - Completed
- `#FFA500` (Orange) - Active
- `#808080` (Gray) - Planned
- `#FF6666` (Red) - On Hold

**Example Requests**:

```bash
# Get all sites
curl "http://localhost:8000/api/ghana-map-project-sites/"

# Get SHEP projects in Ashanti region
curl "http://localhost:8000/api/ghana-map-project-sites/?project_type=SHEP&region=Ashanti"

# Get completed sites
curl "http://localhost:8000/api/ghana-map-project-sites/?site_status=Completed"

# Get active projects in SHEP-4
curl "http://localhost:8000/api/ghana-map-project-sites/?phase=SHEP-4&status=Active"
```

---

### 2. Region Heatmap (`/api/ghana-map-region-heatmap/`)

Returns Ghana's regions with aggregated project statistics for heatmap visualization.

**Method**: `GET`

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_type` | string | Filter by project type |
| `phase` | string | Filter by phase |
| `include_empty` | boolean | Include regions with no projects (default: true) |

**Response**:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": 1,
        "name": "Ashanti",
        "code": "ASH",
        "capital": "Kumasi",
        "population": 4780382,
        "total_sites": 150,
        "completed_sites": 120,
        "active_sites": 20,
        "planned_sites": 10,
        "completion_rate": 80.0,
        "heatmap_color": "#00aa00",
        "district_count": 11
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[...], [...], ...]]
      }
    }
  ],
  "meta": {
    "regions_count": 16,
    "timestamp": "2026-05-18T12:51:00Z"
  }
}
```

**Heatmap Color Mapping**:
- `#00aa00` (Dark Green) - 80%+ completion
- `#AAAA00` (Yellow-Green) - 60-79% completion
- `#FFAA00` (Orange) - 40-59% completion
- `#FF6600` (Red-Orange) - 20-39% completion
- `#FF0000` (Red) - <20% completion

---

### 3. Statistics (`/api/ghana-map-stats/`)

Returns aggregated project and site statistics.

**Method**: `GET`

**Query Parameters**: Same as Project Sites endpoint

**Response**:

```json
{
  "projects": {
    "total": 50,
    "active": 25,
    "completed": 15,
    "planned": 10
  },
  "sites": {
    "total": 500,
    "active": 200,
    "completed": 250,
    "planned": 40,
    "on_hold": 10,
    "overdue": 5,
    "at_risk": 15
  },
  "completion": {
    "percentage": 50.0,
    "by_status": {
      "Completed": 250,
      "Active": 200,
      "Planned": 40,
      "On Hold": 10
    },
    "by_region": {
      "Ashanti": {
        "total": 150,
        "completed": 120,
        "percentage": 80.0
      }
    }
  },
  "budget": {
    "total": 50000000.0,
    "spent": 25000000.0,
    "utilization_percentage": 50.0
  },
  "timestamp": "2026-05-18T12:51:00Z"
}
```

---

### 4. Districts by Region (`/api/ghana-map-districts/`)

Returns districts for a given region (for cascading dropdowns).

**Method**: `GET`

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `region` | string | Yes | Region name |
| `include_stats` | boolean | No | Include site count and completion stats (default: true) |

**Response**:

```json
{
  "region": "Ashanti",
  "districts": [
    {
      "id": 1,
      "name": "Kumasi Metropolitan",
      "code": "KMA",
      "capital": "Kumasi",
      "population": 950000,
      "site_count": 45,
      "completed_sites": 35,
      "completion_percentage": 77.78
    }
  ],
  "count": 11,
  "timestamp": "2026-05-18T12:51:00Z"
}
```

**Example**:

```bash
curl "http://localhost:8000/api/ghana-map-districts/?region=Ashanti"
```

---

### 5. Communities (`/api/ghana-map-communities/`)

Returns communities for a given district with geospatial data.

**Method**: `GET`

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `district` | string | Yes | District name |
| `region` | string | No | Region name (for validation) |

**Response**:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-1.6200, 6.6263]
      },
      "properties": {
        "id": 1,
        "name": "Adum",
        "code": "ADM",
        "district": "Kumasi Metropolitan",
        "region": "Ashanti",
        "population": 50000,
        "chieftain": "Nana Owusu",
        "total_projects": 5,
        "completed_projects": 3
      }
    }
  ],
  "meta": {
    "district": "Kumasi Metropolitan",
    "region": "Ashanti",
    "count": 8,
    "timestamp": "2026-05-18T12:51:00Z"
  }
}
```

---

## Getting Started

### Installation & Setup

1. **Install Dependencies**

```bash
pip install -r requirements.txt
```

2. **Run Migrations**

```bash
python manage.py makemigrations Inventory
python manage.py migrate Inventory
```

3. **Seed Initial Data**

```bash
python manage.py populate_geospatial_data
```

This creates Ghana's 16 regions and all districts.

4. **Create Superuser** (if needed)

```bash
python manage.py createsuperuser
```

5. **Start Server**

```bash
python manage.py runserver
```

6. **Access Ghana Map**

Navigate to: `http://localhost:8000/ghana-map/`

---

## User Guide

### Navigating the Ghana Map

**Map View**:
- Pan: Click and drag the map
- Zoom: Scroll or use zoom buttons (+/-)
- Click any site marker to see details

**Filter Panel** (Left side):
1. Select **Project Type** (SHEP, Turnkey, China Water, etc.)
2. Enter **Phase** (e.g., SHEP-4)
3. Choose **Region** (all 16 Ghana regions)
4. Choose **District** (districts within selected region)
5. Select **Status** (project status)
6. Select **Site Status** (individual site status)
7. Click **Filter** to apply or **Reset** to clear

**View Modes**:
- **Sites**: Shows individual project site markers color-coded by status
- **Heatmap**: Shows regions color-coded by completion percentage

**Statistics Panel** (Bottom right):
- Shows counts of Completed, Active, Planned, and On Hold sites
- Progress bar showing overall completion percentage
- Updates in real-time as filters change

### Understanding Site Markers

**Colors indicate status**:
- 🟢 Green = Completed
- 🟠 Orange = Active
- ⚫ Gray = Planned
- 🔴 Red = On Hold

**Click a marker** to see:
- Site name and code
- Community and location
- Project details
- Status and completion percentage
- Site supervisor
- Dates

---

## Admin Guide

### Managing Regions & Districts

**Add a Region**:

1. Go to Django Admin (`/admin/`)
2. Navigate to **Regions**
3. Click **Add Region**
4. Fill in:
   - Name (unique)
   - Code (e.g., ASH for Ashanti)
   - Capital city
   - Population
   - GeoJSON boundary (optional, for PostGIS)

**Add a District**:

1. Go to Django Admin
2. Navigate to **Districts**
3. Click **Add District**
4. Select parent **Region**
5. Fill in:
   - Name
   - Code
   - Capital
   - Population

### Updating Project Sites with GPS

**Via Admin Panel**:

1. Go to **Project Sites**
2. Edit a site
3. Fill in **Latitude** and **Longitude**
4. Save

**Format**: Latitude and Longitude must be decimal degrees:
- Example: `6.6263` for latitude, `-1.6200` for longitude
- Ghana range: Latitude 1.0 to 11.0, Longitude -3.5 to 1.2

**Bulk Import** (if available):
Use Django's bulk import functionality to add GPS data from CSV/Excel.

### Monitoring Performance

**Check Statistics**:
- Access `/api/ghana-map-stats/` to see real-time metrics
- Compare regions to identify bottlenecks
- Track budget utilization

**Database Optimization**:
- The system uses indexed fields for fast queries
- Suitable for 10,000+ sites on SQLite
- For 50,000+ sites, migrate to PostgreSQL+PostGIS

---

## Deployment

### Production Deployment Checklist

- [ ] Install all requirements from `requirements.txt`
- [ ] Run migrations in production database
- [ ] Seed Ghana regions/districts data
- [ ] Configure allowed hosts in `settings.py`
- [ ] Enable HTTPS/SSL
- [ ] Set `DEBUG=False`
- [ ] Create superuser account
- [ ] Run static files collection: `python manage.py collectstatic --noinput`
- [ ] Configure logging and error tracking
- [ ] Set up database backups
- [ ] Test API endpoints
- [ ] Monitor performance with 100+ concurrent users

### Database Migration (SQLite → PostgreSQL)

If scaling to production:

1. **Install PostgreSQL + PostGIS**
2. **Update settings.py**:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'ghana_map_db',
        'USER': 'user',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

3. **Run migrations**: `python manage.py migrate`
4. **Seed data**: `python manage.py populate_geospatial_data`
5. **Update serializers** to use PostGIS geometry fields

---

## Troubleshooting

### Common Issues

**Issue**: "No markers showing on map"

**Solution**:
- Verify sites have latitude/longitude values
- Check API endpoint responds with valid GeoJSON
- Inspect browser console for JavaScript errors
- Ensure Leaflet.js CDN is accessible

**Issue**: "Map doesn't load"

**Solution**:
- Check OpenStreetMap tiles URL is accessible
- Verify network connectivity
- Check for browser console errors
- Clear browser cache

**Issue**: "Filters not working"

**Solution**:
- Ensure REST framework is installed: `pip install djangorestframework`
- Check API URLs are registered in `urls.py`
- Verify data exists for selected filters

**Issue**: "Slow performance with 1000+ sites"

**Solution**:
- Migrate to PostgreSQL + PostGIS
- Add database indexes
- Use clustering plugin for marker grouping
- Implement pagination for API responses

---

## API Rate Limiting

No rate limiting is currently implemented. For production, consider adding:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}
```

---

## Support & Feedback

For issues or suggestions:
1. Check this documentation
2. Review test cases in `test_geospatial.py`
3. Contact the development team
4. Check GitHub issues

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | May 18, 2026 | Initial release with 5 API endpoints, interactive map, heatmap visualization |

---

**Last Updated**: May 18, 2026  
**Maintained By**: Development Team  
**License**: [Project License]
