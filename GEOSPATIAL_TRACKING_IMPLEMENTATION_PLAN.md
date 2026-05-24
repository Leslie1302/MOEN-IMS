# Ghana Map Rewrite: Geospatial Project Tracking System
## Implementation Plan

---

## **Phase 1: Prerequisites & Dependencies**

### **1.1 Database Setup**
**Objective:** Enable geospatial queries in Django/PostgreSQL

**Tasks:**
- [ ] Install PostGIS extension in PostgreSQL (if not already installed)
  ```sql
  CREATE EXTENSION postgis;
  ```
- [ ] Install Django dependencies:
  ```bash
  pip install django-crispy-forms crispy-bootstrap5 django-rest-framework-gis
  ```
- [ ] Update `INSTALLED_APPS` in settings.py:
  ```python
  INSTALLED_APPS = [
      ...
      'django.contrib.gis',
      'rest_framework',
      'rest_framework_gis',
  ]
  ```
- [ ] Update `DATABASES` in settings.py:
  ```python
  DATABASES = {
      'default': {
          'ENGINE': 'django.contrib.gis.db.backends.postgis',
          'NAME': 'your_db_name',
          ...
      }
  }
  ```

**Estimated Effort:** 1-2 hours

---

## **Phase 2: Data Models**

### **2.1 Create Geography Models**
**File:** `Inventory/models/geography.py` (NEW)

**Models to create:**
- `Region` (Ghana's 16 administrative regions)
- `District` (Districts within regions)
- Update `Package` model to link to District

**Tasks:**
- [ ] Create `Region` model:
  ```python
  class Region(auto_prefetch.Model):
      name = CharField(max_length=100, unique=True)
      code = CharField(max_length=10)
      geom = PolygonField(null=True, blank=True)  # PostGIS boundary
      created_at = DateTimeField(auto_now_add=True)
  ```

- [ ] Create `District` model:
  ```python
  class District(auto_prefetch.Model):
      region = ForeignKey(Region, on_delete=models.CASCADE)
      name = CharField(max_length=100)
      code = CharField(max_length=10)
      geom = PolygonField(null=True, blank=True)
  ```

- [ ] Seed Region data (16 Ghana regions)
- [ ] Seed District data (all 16 districts per region)
- [ ] Create migration: `makemigrations geography`

**Estimated Effort:** 3-4 hours (including data seeding)

---

### **2.2 Update Existing Models**
**Files to modify:**
- `Inventory/models/projects.py`
- `Inventory/models/inventory.py` (if Community model exists)

**Tasks:**
- [ ] Update `Community` model (or create if doesn't exist):
  ```python
  class Community(Model):
      name = CharField(max_length=100)
      region = CharField(max_length=100)
      district = CharField(max_length=100)
      gps_coordinates = PointField(null=True, blank=True)  # PostGIS Point
      latitude = FloatField(null=True, blank=True)
      longitude = FloatField(null=True, blank=True)
  ```

- [ ] Update `Project` model:
  ```python
  # Add/modify fields:
  region = CharField(max_length=100, editable=False)  # From package
  district = CharField(max_length=100, editable=False)  # From package
  ```

- [ ] Update `ProjectSite` model:
  ```python
  # Add fields:
  community = ForeignKey(Community, null=True, on_delete=models.SET_NULL)
  gps_coordinates = PointField(null=True, blank=True)
  latitude = FloatField(null=True, blank=True)
  longitude = FloatField(null=True, blank=True)
  ```

- [ ] Create migration for all changes
- [ ] Run migrations: `migrate`

**Estimated Effort:** 2-3 hours

---

## **Phase 3: Backend API Development**

### **3.1 Create API Serializers**
**File:** `Inventory/serializers/geospatial_serializers.py` (NEW)

**Tasks:**
- [ ] Create `ProjectSiteGeoJSONSerializer`:
  ```python
  class ProjectSiteGeoJSONSerializer(ModelSerializer):
      geometry = SerializerMethodField()
      properties = SerializerMethodField()
      
      def get_geometry(self, obj):
          if obj.gps_coordinates:
              return {
                  'type': 'Point',
                  'coordinates': [obj.longitude, obj.latitude]
              }
          return None
      
      def get_properties(self, obj):
          return {
              'id': obj.id,
              'name': obj.name,
              'community': obj.community_name,
              'status': obj.status,
              'status_color': {...},
              ...
          }
  ```

**Estimated Effort:** 1-2 hours

---

### **3.2 Create API Views**
**File:** `Inventory/views/geospatial_views.py` (NEW)

**API Endpoints to create:**

1. **`ghana_map_project_sites_api`**
   - URL: `/api/ghana-map-project-sites/`
   - Method: GET
   - Params: `project_type`, `phase`, `region`, `district`, `status`
   - Returns: GeoJSON FeatureCollection
   - Tasks:
     - [ ] Build dynamic queryset with filters
     - [ ] Convert to GeoJSON format
     - [ ] Add properties (name, status, colors, etc.)

2. **`ghana_map_region_heatmap_api`**
   - URL: `/api/ghana-map-region-heatmap/`
   - Method: GET
   - Returns: GeoJSON with region polygons + aggregated stats
   - Tasks:
     - [ ] Calculate completion rate per region
     - [ ] Calculate budget utilization per region
     - [ ] Assign color based on completion %
     - [ ] Return region geometries with stats

3. **`ghana_map_stats_api`**
   - URL: `/api/ghana-map-stats/`
   - Method: GET
   - Params: Same filters as sites endpoint
   - Returns: JSON with stats (total, completed, active, planned)
   - Tasks:
     - [ ] Aggregate counts by status
     - [ ] Calculate completion percentage
     - [ ] Filter by parameters

4. **`ghana_map_districts_api`** (optional, for cascading dropdowns)
   - URL: `/api/ghana-map-districts/?region=Ashanti`
   - Returns: Districts in selected region

**Estimated Effort:** 4-5 hours

---

### **3.3 Add URL Routes**
**File:** `Inventory/urls.py` (MODIFY)

**Tasks:**
- [ ] Import new geospatial views
- [ ] Add URL patterns:
  ```python
  path('api/ghana-map-project-sites/', ghana_map_project_sites_api, name='ghana_map_project_sites_api'),
  path('api/ghana-map-region-heatmap/', ghana_map_region_heatmap_api, name='ghana_map_region_heatmap_api'),
  path('api/ghana-map-stats/', ghana_map_stats_api, name='ghana_map_stats_api'),
  path('api/ghana-map-districts/', ghana_map_districts_api, name='ghana_map_districts_api'),
  ```

**Estimated Effort:** 0.5 hours

---

## **Phase 4: Frontend Development**

### **4.1 Create Enhanced Ghana Map Template**
**File:** `Inventory/templates/Inventory/ghana_map_enhanced.html` (NEW)

**Components:**
- [ ] Header with page title and description
- [ ] Filter control panel (project type, phase, region, status)
- [ ] Map container (id="map")
- [ ] View mode toggle (Sites / Heatmap)
- [ ] Bottom-right stats panel
- [ ] Responsive layout

**Estimated Effort:** 2-3 hours

---

### **4.2 Implement Frontend JavaScript**
**File:** `Inventory/templates/Inventory/ghana_map_enhanced.html` (inline scripts)

**Tasks:**
- [ ] Initialize Leaflet map
  ```javascript
  const map = L.map('map').setView([6.5, -2.0], 7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
  ```

- [ ] Implement `loadProjectData()` function:
  - [ ] Build query parameters from filters
  - [ ] Fetch GeoJSON from API
  - [ ] Clear existing markers
  - [ ] Add new markers with colors by status
  - [ ] Bind popups with project details
  - [ ] Update stats panel

- [ ] Implement `loadHeatmapData()` function:
  - [ ] Fetch region GeoJSON
  - [ ] Color regions by completion rate
  - [ ] Add region stats to popups

- [ ] Implement filter event listeners:
  - [ ] On project type change → reload data
  - [ ] On phase change → reload data
  - [ ] On region change → reload data
  - [ ] On status change → reload data

- [ ] Implement view mode toggle:
  - [ ] Radio buttons for Sites / Heatmap
  - [ ] Clear layers and switch views
  - [ ] Maintain filter state when switching

- [ ] Implement stats update:
  - [ ] Calculate total, completed, active, planned
  - [ ] Calculate completion percentage
  - [ ] Update progress bar
  - [ ] Update stat cards

**Estimated Effort:** 5-6 hours

---

### **4.3 Add CSS Styling**
**File:** `Inventory/templates/Inventory/ghana_map_enhanced.html` (inline styles or static CSS)

**Tasks:**
- [ ] Style filter panel (clean, organized)
- [ ] Style stats panel (floating, responsive)
- [ ] Style popup content (readable, compact)
- [ ] Responsive breakpoints (mobile, tablet, desktop)
- [ ] Add color-coded status badges
- [ ] Progress bar styling

**Estimated Effort:** 1-2 hours

---

## **Phase 5: Update Project Views**

### **5.1 Modify Project Form**
**File:** `Inventory/forms/project_forms.py` (MODIFY)

**Tasks:**
- [ ] Add Package field to ProjectCreateForm
- [ ] Add region, district dropdowns (filtered by package selection)
- [ ] Add district → package cascade filter
- [ ] Auto-populate region/district from package
- [ ] Make fields read-only if derived from package

**Estimated Effort:** 2-3 hours

---

### **5.2 Update Project Views**
**File:** `Inventory/views/project_views.py` (MODIFY)

**Tasks:**
- [ ] Update `ProjectCreateView`:
  - [ ] Add Package selection step
  - [ ] Auto-create ProjectSites from package communities
  - [ ] Set GPS coordinates from Community model

- [ ] Update `ProjectListView`:
  - [ ] Add region/district filters
  - [ ] Show region in list display
  - [ ] Show site count and completion %

- [ ] Update `ProjectDetailView`:
  - [ ] Display project on mini-map
  - [ ] Show all sites with GPS markers
  - [ ] Show completion stats by district

**Estimated Effort:** 3-4 hours

---

### **5.3 Update Project Detail Template**
**File:** `Inventory/templates/Inventory/project_detail.html` (MODIFY)

**Tasks:**
- [ ] Add embedded mini-map showing project sites
- [ ] Show sites table with GPS coordinates
- [ ] Show completion rate progress bar
- [ ] Link to main Ghana Map with project filter pre-applied
- [ ] Add "View on Map" button

**Estimated Effort:** 2-3 hours

---

## **Phase 6: Data Integration**

### **6.1 Create Data Migration Script**
**File:** `Inventory/management/commands/populate_geospatial_data.py` (NEW)

**Tasks:**
- [ ] Script to populate Region/District data
- [ ] Script to load PostGIS region boundaries (optional, from GeoJSON)
- [ ] Script to populate GPS coordinates for Communities
- [ ] Script to link Projects to Packages/Regions

**Estimated Effort:** 2-3 hours

---

### **6.2 Data Import**
**Tasks:**
- [ ] Run population scripts
- [ ] Verify data integrity
- [ ] Test API endpoints with real data
- [ ] Spot-check GPS coordinates on map

**Estimated Effort:** 1-2 hours

---

## **Phase 7: Testing & Refinement**

### **7.1 Unit Tests**
**File:** `Inventory/tests/test_geospatial.py` (NEW)

**Tests to write:**
- [ ] Test Region model creation
- [ ] Test District model creation
- [ ] Test Project creation with Package
- [ ] Test ProjectSite auto-creation from package communities
- [ ] Test API filtering (by project type, phase, region, status)
- [ ] Test GeoJSON serialization

**Estimated Effort:** 3-4 hours

---

### **7.2 Integration Tests**
**Tasks:**
- [ ] Test full workflow: Create project → Create sites → View on map
- [ ] Test filters on Ghana Map
- [ ] Test heatmap calculation
- [ ] Test view switching (Sites / Heatmap)
- [ ] Test responsive design on mobile/tablet
- [ ] Test performance with 1000+ sites
- [ ] Test popup interactions

**Estimated Effort:** 3-4 hours

---

### **7.3 UI/UX Polish**
**Tasks:**
- [ ] Refine filter panel layout
- [ ] Optimize marker sizes/colors for visibility
- [ ] Improve popup design (readability, compact)
- [ ] Add loading indicators for API calls
- [ ] Add error messages for failed API calls
- [ ] Improve stats panel visibility
- [ ] Test on various screen sizes

**Estimated Effort:** 2-3 hours

---

## **Phase 8: Documentation & Deployment**

### **8.1 Documentation**
**Files to create:**
- [ ] API documentation (endpoints, params, responses)
- [ ] User guide for Ghana Map (features, filters, usage)
- [ ] Admin guide (updating regions, districts, GPS data)

**Estimated Effort:** 2-3 hours

---

### **8.2 Deployment Prep**
**Tasks:**
- [ ] Database backup before migrations
- [ ] Run migrations in staging environment
- [ ] Test all API endpoints in staging
- [ ] Verify Leaflet/CDN resources load correctly
- [ ] Check for console errors in browser DevTools
- [ ] Verify performance (map loads in <2 seconds)

**Estimated Effort:** 1-2 hours

---

### **8.3 Production Deployment**
**Tasks:**
- [ ] Run migrations in production
- [ ] Populate geospatial data
- [ ] Test Ghana Map in production
- [ ] Monitor error logs
- [ ] Verify stats accuracy

**Estimated Effort:** 1-2 hours

---

## **Phase 9: Optional Enhancements**

### **9.1 Advanced Features** (Post-MVP)
- [ ] Add route tracking for transporters
- [ ] Add progress timeline (sites completed over time)
- [ ] Add comparison maps (plan vs. actual)
- [ ] Add budget heatmap (spending per region)
- [ ] Export map as PDF/image
- [ ] Mobile app integration

---

## **Files to Create/Modify**

### **Create (NEW):**
- `Inventory/models/geography.py`
- `Inventory/serializers/geospatial_serializers.py`
- `Inventory/views/geospatial_views.py`
- `Inventory/templates/Inventory/ghana_map_enhanced.html`
- `Inventory/management/commands/populate_geospatial_data.py`
- `Inventory/tests/test_geospatial.py`
- `GEOSPATIAL_TRACKING_IMPLEMENTATION_PLAN.md` (this file)

### **Modify (EXISTING):**
- `Inventory/urls.py` (add geospatial routes)
- `Inventory/models/projects.py` (add region, district, coordinates fields)
- `Inventory/models/__init__.py` (import new models)
- `Inventory/forms/project_forms.py` (update project form)
- `Inventory/views/project_views.py` (update project views)
- `Inventory/templates/Inventory/project_detail.html` (add mini-map)
- `Inventory/templates/Inventory/project_list.html` (add region filter)
- Django `settings.py` (add PostGIS, DRF-GIS)

---

## **Dependencies & Tools**

### **Python Packages:**
- django-crispy-forms
- crispy-bootstrap5
- djangorestframework
- djangorestframework-gis
- psycopg2-binary (if not already installed)

### **Database:**
- PostgreSQL with PostGIS extension

### **Frontend Libraries:**
- Leaflet.js (mapping)
- Leaflet-heat (heatmap plugin)
- Bootstrap 5 (already in project)
- OpenStreetMap tiles (free, no API key needed)

### **Optional:**
- Mapbox (alternative to OSM)
- Turf.js (geospatial analysis on client)

---

## **Timeline Estimate**

| Phase | Tasks | Hours | Days |
|-------|-------|-------|------|
| 1. Prerequisites | DB setup, dependencies | 1-2 | 0.25-0.5 |
| 2. Data Models | Create/update models | 5-7 | 1-1.5 |
| 3. Backend APIs | Serializers, views, routes | 5-7 | 1-1.5 |
| 4. Frontend | Template, JS, CSS | 8-10 | 2-2.5 |
| 5. Project Views | Update forms, views, templates | 5-7 | 1-1.5 |
| 6. Data Integration | Scripts, import, verify | 3-5 | 0.75-1 |
| 7. Testing | Unit, integration, UI tests | 8-10 | 2-2.5 |
| 8. Documentation | User guide, API docs | 2-3 | 0.5-0.75 |
| 9. Deployment | Staging, production, monitoring | 2-3 | 0.5-0.75 |
| **TOTAL** | | **42-54 hours** | **10-13 days** |

---

## **Success Criteria**

- [ ] Ghana Map displays all project sites with GPS coordinates
- [ ] Filter by project type, phase, region, status works correctly
- [ ] Heatmap shows completion rate per region
- [ ] Click site → view project details
- [ ] Stats panel updates correctly based on filters
- [ ] View switching (Sites / Heatmap) works smoothly
- [ ] Mobile responsive design works
- [ ] All API endpoints return valid GeoJSON
- [ ] Performance: map loads in <2 seconds
- [ ] Zero console errors
- [ ] Full test coverage (unit + integration)

---

## **Risk Mitigation**

| Risk | Mitigation |
|------|-----------|
| PostGIS installation issues | Use Docker with pre-installed PostGIS |
| GPS coordinate data missing | Provide bulk import tool, allow manual entry |
| Map performance with 1000+ sites | Use clustering plugin, pagination |
| Mobile responsiveness issues | Test early and often on devices |
| Browser compatibility | Use established libraries (Leaflet is widely supported) |

---

## **Next Steps**

1. Review this plan with stakeholders
2. Confirm technology stack (PostGIS, Leaflet, etc.)
3. Prioritize phases (MVP vs. nice-to-have)
4. Start with Phase 1 (prerequisites) to validate setup
5. Execute phases sequentially, testing after each phase

