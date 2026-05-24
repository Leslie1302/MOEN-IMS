# Ghana Map Implementation - Quick Test Guide

## What's New
The Ghana Map dashboard metric cards are now fully functional and clickable. Each card redirects to a dedicated detail page showing comprehensive data about that metric.

## Navigation Flow

```
/ghana-map/ (Main Dashboard)
    ↓
    ├─→ Click "Total Sites Nationwide" → /ghana-map-total-sites/
    ├─→ Click "Completed Sites" → /ghana-map-completed-sites/
    ├─→ Click "Active / In-Progress" → /ghana-map-active-sites/
    └─→ Click "National Progress" → /ghana-map-progress/
    
Each detail page → Click "← Back to Map" → Returns to /ghana-map/
```

## Testing Checklist

### 1. Main Dashboard
- [ ] Navigate to http://localhost:8000/ghana-map/
- [ ] Verify 4 metric cards are visible:
  - [ ] Total Sites Nationwide (blue background)
  - [ ] Completed Sites (green background)
  - [ ] Active / In-Progress Sites (yellow background)
  - [ ] National Progress % (cyan background)
- [ ] Verify cards have pointer cursor on hover
- [ ] Verify cards have subtle shadow/highlight effect

### 2. Total Sites Page
- [ ] Click "Total Sites Nationwide" card
- [ ] Verify redirect to `/ghana-map-total-sites/`
- [ ] Check statistics display (Total, Completed, Active, Planned)
- [ ] Check table loads with all sites listed
- [ ] Table should show: Site Name, Code, Region, District, Status, Completion %
- [ ] Verify status pills are color-coded
- [ ] Click "← Back to Map" button
- [ ] Verify redirect back to main dashboard

### 3. Completed Sites Page
- [ ] Click "Completed Sites" card
- [ ] Verify redirect to `/ghana-map-completed-sites/`
- [ ] Check statistics display (Total Completed count)
- [ ] Check table loads with only completed sites
- [ ] Table should show: Site Name, Code, Region, District, Community, Completion Date
- [ ] Click "← Back to Map" button
- [ ] Verify redirect back to main dashboard

### 4. Active Sites Page
- [ ] Click "Active / In-Progress Sites" card
- [ ] Verify redirect to `/ghana-map-active-sites/`
- [ ] Check statistics display (Currently Active count)
- [ ] Check table loads with only active sites
- [ ] Table should show: Site Name, Code, Region, District, Supervisor, Progress bar
- [ ] Verify progress bars display completion percentage
- [ ] Click "← Back to Map" button
- [ ] Verify redirect back to main dashboard

### 5. National Progress Page
- [ ] Click "National Progress" card
- [ ] Verify redirect to `/ghana-map-progress/`
- [ ] Check statistics display (Overall Progress %, Completed, Active, Planned)
- [ ] Check regional breakdown section loads
- [ ] Each region should show: Name, Progress bar, Completed/Active/Total counts, Percentage
- [ ] Click "← Back to Map" button
- [ ] Verify redirect back to main dashboard

## API Endpoints to Test

You can test these endpoints directly using curl or a REST client:

```bash
# Get all project sites
curl http://localhost:8000/api/ghana-map-project-sites/ -H "Authorization: Token YOUR_TOKEN"

# Get stats
curl http://localhost:8000/api/ghana-map-stats/ -H "Authorization: Token YOUR_TOKEN"

# Get regional heatmap data
curl http://localhost:8000/api/ghana-map-region-heatmap/ -H "Authorization: Token YOUR_TOKEN"

# Get districts for a region
curl "http://localhost:8000/api/ghana-map-districts/?region=Greater%20Accra" -H "Authorization: Token YOUR_TOKEN"

# Get communities for a district
curl "http://localhost:8000/api/ghana-map-communities/?district=Accra%20Metropolitan" -H "Authorization: Token YOUR_TOKEN"
```

Replace `YOUR_TOKEN` with a valid authentication token from your Django session.

## Expected Response Examples

### /api/ghana-map-stats/
```json
{
  "projects": {
    "total": 10,
    "active": 3,
    "completed": 5,
    "planned": 2
  },
  "sites": {
    "total": 45,
    "active": 12,
    "completed": 25,
    "planned": 8,
    "on_hold": 0,
    "overdue": 2,
    "at_risk": 3
  },
  "completion": {
    "percentage": 55.56,
    "by_status": {
      "Completed": 25,
      "Active": 12,
      "Planned": 8,
      "On Hold": 0
    },
    "by_region": {
      "Greater Accra": {...},
      ...
    }
  },
  "budget": {...},
  "timestamp": "2026-05-18T..."
}
```

### /api/ghana-map-project-sites/
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [lon, lat]
      },
      "properties": {
        "id": 1,
        "name": "Site Name",
        "code": "SITE001",
        "region": "Greater Accra",
        "district": "Accra Metropolitan",
        "status": "Active",
        "completion_percentage": 45.5,
        ...
      }
    },
    ...
  ],
  "meta": {
    "count": 45,
    "timestamp": "2026-05-18T..."
  }
}
```

## Troubleshooting

### Cards Not Clickable
- [ ] Check browser console for JavaScript errors (F12 → Console)
- [ ] Verify metric cards have `id="card-total"`, `id="card-completed"`, etc.
- [ ] Check that event listeners are being attached

### Pages Not Loading
- [ ] Verify authentication is working (you should be logged in)
- [ ] Check browser console for 404 errors
- [ ] Verify API endpoints are enabled in urls.py
- [ ] Check Django server logs for any errors

### API Returning 404
- [ ] Verify API routes are uncommented in urls.py
- [ ] Check that geospatial_views.py is imported correctly
- [ ] Verify ProjectSite model has required fields
- [ ] Check that serializers are available

### API Returning 403
- [ ] Verify you're authenticated
- [ ] Check Django login/authentication configuration
- [ ] Verify user permissions

### No Data Showing
- [ ] Check if ProjectSite database has any records
- [ ] Verify region/district data is populated
- [ ] Check API response in browser DevTools (Network tab)
- [ ] Look for error messages in console

## Performance Notes
- All data is fetched asynchronously, so pages should load quickly
- Detail pages may take a moment to load if you have many project sites
- Consider implementing pagination if dataset becomes very large

## Browser Compatibility
- Chrome/Edge: ✓ Fully supported
- Firefox: ✓ Fully supported
- Safari: ✓ Fully supported
- IE11: ✗ Not supported (uses Fetch API)

## Success Criteria
✓ All metric cards redirect to correct pages
✓ All API endpoints return data without errors
✓ Detail pages display data in formatted tables
✓ Back buttons return to main dashboard
✓ No 404 or 500 errors in console
✓ All tables render correctly with proper styling
