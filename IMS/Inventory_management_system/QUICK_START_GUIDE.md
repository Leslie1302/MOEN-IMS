# Quick Start Guide: Package-Based Tracking

## 🚀 Getting Started

### Step 1: Apply Migrations
```bash
python3 manage.py migrate
```

### Step 2: Access New Features

#### **Contract Packages** (NEW)
- **URL:** `/contract-packages/`
- **Purpose:** View and manage contract packages with community lists
- **Who can access:** All authenticated users

---

## 📝 How to Use

### **A. Managing Contract Packages**

#### 1. **View All Packages**
- Navigate to: `/contract-packages/`
- See: Package list with BOQ statistics and community counts

#### 2. **Upload Contract Packages**
- Click: "Upload Packages" button
- Download template: `contract_package_template.xlsx`
- Fill in columns:
  - **Required:** package_number, project_name, region, district, communities, consultant, contractor
  - **Optional:** contract_value, start_date, end_date, status, notes
- **Communities format:** "Community A, Community B, Community C"
- Upload Excel file

#### 3. **View Package Details**
- Click: "View" button on any package
- See:
  - Package information
  - List of communities
  - BOQ summary statistics
  - Related BOQ items with progress

---

### **B. Uploading Bill of Quantity (BOQ)**

#### **NEW Format - No Community Column**

**Required Columns:**
- region
- district
- consultant
- contractor
- package_number
- material_description
- contract_quantity
- quantity_received

**Template:** Use `boq_upload_template.xlsx`

**Example:**
```
region       | district  | consultant      | contractor | package_number | material_description | contract_quantity | quantity_received
Northern     | Tamale    | ABC Consultants | BuildCo    | PKG-001       | Concrete Poles      | 1000             | 0
Greater Accra| Accra     | XYZ Engineering | ConstructPro| PKG-002      | Steel Wires         | 500              | 0
```

**Important:** 
- ❌ **DO NOT** include a `community` column
- ✅ Quantities are **package totals**, not per-community
- ✅ Material descriptions must match existing inventory items

---

### **C. Requesting Materials (Bulk Upload)**

#### **NEW Format - No Community Column**

**Required Columns:**
- name
- quantity
- region
- district
- consultant
- contractor
- package_number
- warehouse

**Template:** Use `bulk_request_template_updated.xlsx`

**Example:**
```
name            | quantity | region    | district | consultant      | contractor | package_number | warehouse
Concrete Poles  | 50       | Northern  | Tamale   | ABC Consultants | BuildCo    | PKG-001       | Main Warehouse
Steel Wires     | 100      | Greater Accra | Accra | XYZ Engineering | ConstructPro | PKG-002     | Regional Store
```

**Important:**
- ❌ **DO NOT** include a `community` column
- ✅ Requests are for package totals
- ✅ See Contract Packages list for community reference

---

## 🔄 Workflow Comparison

### **Before (Community-Based):**
1. Upload BOQ with community column
2. Each community = separate BOQ entry
3. Request materials per community

### **After (Package-Based):**
1. Upload Contract Packages (with communities list) ← **NEW STEP**
2. Upload BOQ without community column (package totals)
3. Request materials per package
4. View community information in Contract Packages list

---

## 📊 Where to Find Communities

**Old Way:** Communities in BOQ/Material Order records
**New Way:** Communities in Contract Packages

**To find communities for a package:**
1. Go to: `/contract-packages/`
2. Find your package
3. Click "View"
4. See communities list

---

## 🎯 Key Changes

| Feature | Old System | New System |
|---------|------------|------------|
| **BOQ Tracking** | Per community | Per package (total) |
| **Material Orders** | Per community | Per package |
| **Communities** | In every record | In Contract Packages (reference) |
| **BOQ Upload** | With community column | Without community column |
| **Excel Templates** | Include community | Exclude community |
| **Package View** | N/A | Shows all communities |

---

## ✅ Checklist for New Users

- [ ] Apply migrations: `python3 manage.py migrate`
- [ ] Download new Excel templates
- [ ] Upload Contract Packages (if needed)
- [ ] Upload BOQ using new format (no community column)
- [ ] Create material orders using new format
- [ ] View Contract Packages to see community lists

---

## 📥 Template Downloads

Place templates in `/media/templates/` or provide download links:

1. **boq_upload_template.xlsx** - BOQ upload (no community)
2. **bulk_request_template_updated.xlsx** - Material orders (no community)
3. **contract_package_template.xlsx** - Contract packages with communities

---

## ⚠️ Common Mistakes

### ❌ **Don't:**
- Include community column in BOQ uploads
- Include community column in material order uploads
- Try to track per-community quantities in BOQ

### ✅ **Do:**
- Upload Contract Packages first (with communities)
- Use package totals in BOQ
- Reference Contract Packages list for community information
- Use new Excel templates without community column

---

## 🆘 Troubleshooting

### **Error: Missing column 'community'**
- **Solution:** You're using old template. Download new templates without community column.

### **Can't find community information**
- **Solution:** Check Contract Packages list (`/contract-packages/`)

### **BOQ quantities seem wrong**
- **Note:** BOQ now shows package totals, not per-community quantities. This is expected.

### **Old uploads not working**
- **Solution:** Update your Excel files to remove community column and use package totals.

---

## 📞 Need Help?

1. Review `PACKAGE_BASED_TRACKING_MIGRATION.md` for detailed information
2. Check Excel templates for correct format
3. Verify migrations are applied
4. Test with small dataset first

---

**Last Updated:** October 29, 2025
