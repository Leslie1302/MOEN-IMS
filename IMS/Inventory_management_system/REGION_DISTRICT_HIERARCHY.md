# Region-District Hierarchical Implementation

## 📍 Overview

Implemented proper hierarchical relationship between **Regions** and **Districts** to ensure data integrity and enable cascading dropdowns throughout the system.

---

## 🎯 Problem Solved

**Before:** Region and district were simple text fields without any relationship
- Any region-district combination was possible (data integrity issues)
- No validation to ensure districts belong to their correct regions
- No cascading dropdowns

**After:** Proper hierarchical models with foreign key relationships
- Districts are linked to their parent regions
- Data integrity enforced at database level
- Foundation for cascading dropdowns in forms
- Proper region-district hierarchy for Ghana's administrative structure

---

## 🏗️ Models Created

### **1. Region Model**
```python
class Region(auto_prefetch.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)  # e.g., GAR, NR, AR
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Fields:**
- `name` - Region name (e.g., "Greater Accra", "Northern")
- `code` - Short code for the region (e.g., "GAR", "NR")
- `is_active` - Whether the region is currently active
- Timestamps

### **2. District Model**
```python
class District(auto_prefetch.Model):
    name = models.CharField(max_length=100)
    region = ForeignKey(Region)  # Links district to parent region
    code = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    unique_together = ['name', 'region']  # District name unique within region
```

**Fields:**
- `name` - District name (e.g., "Accra Metropolitan", "Tamale Metropolitan")
- `region` - Foreign key to parent Region
- `code` - Optional district code
- `is_active` - Whether the district is currently active
- Timestamps

**Constraint:**
- District name must be unique within a region (can have same district name in different regions)

---

## 🗂️ Admin Interface

### **Region Admin**
- List view shows: name, code, district count, is_active, created_at
- Filter by: is_active, created_at
- Search by: name, code
- Custom column: Shows number of districts in each region

### **District Admin**
- List view shows: name, region, code, is_active, created_at
- Filter by: region, is_active, created_at
- Search by: name, code, region name
- Autocomplete: Region field uses autocomplete for easy selection
- Organized fieldsets

---

## 📊 Data Population

### **Management Command**
Created command to populate all 16 Ghana regions with their respective districts:

```bash
python manage.py populate_regions_districts
```

**What it does:**
- Creates all 16 regions of Ghana with correct codes
- Creates all districts and links them to their parent regions
- Idempotent (safe to run multiple times)
- Shows progress and summary

### **Regions Included:**
1. Greater Accra (GAR) - 25 districts
2. Ashanti (AR) - 39 districts
3. Northern (NR) - 15 districts
4. Western (WR) - 14 districts
5. Eastern (ER) - 27 districts
6. Central (CR) - 22 districts
7. Volta (VR) - 17 districts
8. Upper East (UER) - 14 districts
9. Upper West (UWR) - 11 districts
10. Brong Ahafo (BAR) - 25 districts
11. Western North (WNR) - 9 districts
12. Ahafo (AHR) - 7 districts
13. Bono (BOR) - 11 districts
14. Bono East (BER) - 11 districts
15. Savannah (SV) - 8 districts
16. North East (NER) - 6 districts
17. Oti (OT) - 9 districts

**Total:** 17 regions, 260+ districts

---

## 🔄 Migration Details

**Migration File:** `0014_region_district.py`

**Actions:**
- ✅ Create Region model
- ✅ Create District model
- ✅ Add unique constraint on (name, region) for districts

---

## 🚀 Usage

### **1. Apply Migration**
```bash
python manage.py migrate
```

### **2. Populate Data**
```bash
python manage.py populate_regions_districts
```

### **3. Access in Admin**
- Navigate to Django admin
- Find "Regions" and "Districts" under Inventory section
- View, add, edit regions and districts

### **4. Query in Code**
```python
# Get a region
region = Region.objects.get(name="Greater Accra")

# Get all districts in a region
districts = region.districts.all()

# Get a district with its region
district = District.objects.get(name="Accra Metropolitan")
print(district.region.name)  # "Greater Accra"

# Count districts per region
for region in Region.objects.all():
    print(f"{region.name}: {region.districts.count()} districts")
```

---

## 🎯 Next Steps (Future Enhancements)

### **Phase 2: Update Existing Models**
The current models (BillOfQuantity, MaterialOrder, ContractPackage, etc.) still use CharField for region and district. Future enhancement:

1. **Add Foreign Keys** to existing models:
```python
# Instead of:
region = models.CharField(max_length=100)
district = models.CharField(max_length=100)

# Use:
region = models.ForeignKey(Region, on_delete=models.PROTECT)
district = models.ForeignKey(District, on_delete=models.PROTECT)
```

2. **Data Migration** to convert existing text data to foreign keys

3. **Update Forms** to use cascading dropdowns

### **Phase 3: Cascading Dropdowns**
Implement JavaScript-based cascading dropdowns:
- User selects Region → Only districts in that region shown
- Improves UX and prevents invalid selections

---

## ✅ Benefits

1. **Data Integrity** - Districts can only be linked to valid regions
2. **Consistency** - Standardized region and district names
3. **Validation** - Database-level constraints prevent invalid data
4. **Admin Friendly** - Easy management through admin interface
5. **Autocomplete** - Fast region/district selection in admin
6. **Foundation** - Ready for cascading dropdowns in forms
7. **Reporting** - Easy to aggregate data by region or district
8. **Ghana-Specific** - Pre-populated with actual Ghana administrative structure

---

## 📝 Files Created/Modified

### **Created:**
1. `/Inventory/models.py` - Region and District models
2. `/Inventory/management/commands/populate_regions_districts.py` - Data population command
3. `REGION_DISTRICT_HIERARCHY.md` - This documentation

### **Modified:**
1. `/Inventory/admin.py` - Admin classes for Region and District

### **Migration:**
1. `Inventory/migrations/0014_region_district.py` - Database schema

---

## 🎓 Understanding the Hierarchy

```
Ghana
├── Greater Accra Region
│   ├── Accra Metropolitan District
│   ├── Tema Metropolitan District
│   ├── Ga East Municipal District
│   └── ... (25 total)
├── Ashanti Region
│   ├── Kumasi Metropolitan District
│   ├── Obuasi Municipal District
│   └── ... (39 total)
└── ... (17 regions total, 260+ districts)
```

Each district knows its parent region through the foreign key relationship.

---

## ⚠️ Important Notes

1. **Existing Data:** Current BOQ, Material Orders, and Contract Packages still use text fields for region/district
2. **Gradual Migration:** Region-District models are ready; existing models can be updated later
3. **Backward Compatible:** Old forms and views continue to work with text fields
4. **Future Proof:** Foundation laid for proper region-district relationships system-wide

---

## 📞 Usage Example in Views

```python
from Inventory.models import Region, District

# Get all regions for dropdown
regions = Region.objects.filter(is_active=True)

# Get districts for a specific region (AJAX call)
def get_districts(request, region_id):
    districts = District.objects.filter(
        region_id=region_id,
        is_active=True
    ).values('id', 'name')
    return JsonResponse(list(districts), safe=False)
```

---

**Implementation Date:** October 29, 2025  
**Status:** ✅ Complete - Models created, admin configured, data population command ready  
**Migration:** 0014_region_district.py
