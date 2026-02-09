"""
SHEP Community Management Views

This module provides CRUD views for managing SHEP communities and packages,
along with AJAX endpoints for cascading dropdowns and the abbreviation legend page.
"""
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from django.contrib import messages
import uuid
import random
import string
import io

from .models import SHEPCommunity, MaterialOrder, generate_abbreviation, InventoryItem, Warehouse
from .forms import SHEPCommunityForm


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to require superuser access."""
    def test_func(self):
        return self.request.user.is_superuser


class SHEPCommunityListView(SuperuserRequiredMixin, ListView):
    """List all SHEP communities with their packages."""
    model = SHEPCommunity
    template_name = 'Inventory/shep_community_list.html'
    context_object_name = 'communities'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by search query
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(region__icontains=search) |
                Q(district__icontains=search) |
                Q(community__icontains=search) |
                Q(package_number__icontains=search)
            )
        
        # Filter by region
        region = self.request.GET.get('region', '')
        if region:
            queryset = queryset.filter(region=region)
        
        return queryset.order_by('region', 'district', 'community')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['regions'] = SHEPCommunity.objects.values_list('region', flat=True).distinct().order_by('region')
        context['search'] = self.request.GET.get('search', '')
        context['selected_region'] = self.request.GET.get('region', '')
        return context


class SHEPCommunityCreateView(SuperuserRequiredMixin, CreateView):
    """Create a new SHEP community."""
    model = SHEPCommunity
    form_class = SHEPCommunityForm
    template_name = 'Inventory/shep_community_form.html'
    success_url = reverse_lazy('shep_community_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Community created successfully.')
        return super().form_valid(form)


class SHEPCommunityUpdateView(SuperuserRequiredMixin, UpdateView):
    """Update an existing SHEP community."""
    model = SHEPCommunity
    form_class = SHEPCommunityForm
    template_name = 'Inventory/shep_community_form.html'
    success_url = reverse_lazy('shep_community_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Community updated successfully.')
        return super().form_valid(form)


class SHEPCommunityDeleteView(SuperuserRequiredMixin, DeleteView):
    """Delete a SHEP community."""
    model = SHEPCommunity
    template_name = 'Inventory/shep_community_confirm_delete.html'
    success_url = reverse_lazy('shep_community_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Community deleted successfully.')
        return super().delete(request, *args, **kwargs)


class AbbreviationLegendView(LoginRequiredMixin, TemplateView):
    """Display abbreviation legend showing full names and their abbreviations."""
    template_name = 'Inventory/abbreviation_legend.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get unique regions with abbreviations
        regions = SHEPCommunity.objects.values('region', 'region_abbr').distinct().order_by('region')
        
        # Get unique districts with abbreviations
        districts = SHEPCommunity.objects.values('district', 'district_abbr', 'region').distinct().order_by('region', 'district')
        
        # Get unique communities with abbreviations
        communities = SHEPCommunity.objects.values('community', 'community_abbr', 'district', 'region').distinct().order_by('region', 'district', 'community')
        
        context['regions'] = regions
        context['districts'] = districts
        context['communities'] = communities
        return context


# AJAX Endpoints for Cascading Dropdowns

def get_districts_by_region(request):
    """AJAX endpoint to get districts for a selected region."""
    region = request.GET.get('region', '')
    if not region:
        return JsonResponse({'districts': []})
    
    districts = SHEPCommunity.objects.filter(
        region=region,
        is_active=True
    ).values('district', 'district_abbr').distinct().order_by('district')
    
    district_list = [
        {'name': d['district'], 'abbreviation': d['district_abbr'] or generate_abbreviation(d['district'])}
        for d in districts
    ]
    
    return JsonResponse({'districts': district_list})


def get_communities_by_district(request):
    """AJAX endpoint to get communities for a selected district."""
    district = request.GET.get('district', '')
    region = request.GET.get('region', '')
    
    if not district:
        return JsonResponse({'communities': []})
    
    queryset = SHEPCommunity.objects.filter(
        district=district,
        is_active=True
    )
    if region:
        queryset = queryset.filter(region=region)
    
    communities = queryset.values('community', 'community_abbr').distinct().order_by('community')
    
    community_list = [
        {'name': c['community'], 'abbreviation': c['community_abbr'] or generate_abbreviation(c['community'])}
        for c in communities
    ]
    
    return JsonResponse({'communities': community_list})


def get_packages_by_community(request):
    """AJAX endpoint to get packages for a selected community (SHEP only)."""
    community = request.GET.get('community', '')
    district = request.GET.get('district', '')
    region = request.GET.get('region', '')
    
    if not community:
        return JsonResponse({'packages': []})
    
    queryset = SHEPCommunity.objects.filter(
        community=community,
        is_active=True
    )
    if district:
        queryset = queryset.filter(district=district)
    if region:
        queryset = queryset.filter(region=region)
    
    packages = queryset.values_list('package_number', flat=True).distinct().order_by('package_number')
    
    return JsonResponse({'packages': list(packages)})


def generate_auto_package_number(request):
    """
    AJAX endpoint to generate an auto package number for Cost-sharing/Special projects.
    Format: [PREFIX]-[DISTRICT_ABBR]-[COMMUNITY_ABBR]-[REQUESTOR_ABBR]-[RANDOM]
    """
    project_type = request.GET.get('project_type', 'COST')
    district = request.GET.get('district', '')
    community = request.GET.get('community', '')
    requestor = request.GET.get('requestor', '')
    
    # Get prefix based on project type
    prefix = 'COST' if project_type == 'COST' else 'SPEC'
    
    # Get abbreviations
    district_abbr = generate_abbreviation(district) if district else 'XX'
    community_abbr = generate_abbreviation(community) if community else 'XX'
    requestor_abbr = generate_abbreviation(requestor) if requestor else 'XX'
    
    # Generate random suffix
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    
    # Build package number
    package_number = f"{prefix}-{district_abbr}-{community_abbr}-{requestor_abbr}-{random_suffix}"
    
    return JsonResponse({
        'package_number': package_number,
        'district_abbr': district_abbr,
        'community_abbr': community_abbr,
        'requestor_abbr': requestor_abbr
    })


def download_material_template(request):
    """
    Generate and download an Excel template for bulk material requests.
    Includes new columns: project_type, requestor, community.
    """
    try:
        import pandas as pd
        from openpyxl import Workbook
        from openpyxl.utils.dataframe import dataframe_to_rows
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.styles import Font, Fill, PatternFill, Alignment
    except ImportError:
        return HttpResponse(
            "Required packages not installed. Please install pandas and openpyxl.",
            status=500
        )
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Material Request Template"
    
    # Define columns
    columns = [
        'name',
        'quantity',
        'project_type',
        'requestor',
        'region',
        'district',
        'community',
        'consultant',
        'contractor',
        'package_number',
        'warehouse'
    ]
    
    # Add header row
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col_idx, col_name in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # Adjust column widths
    column_widths = {
        'A': 30,  # name
        'B': 12,  # quantity
        'C': 15,  # project_type
        'D': 25,  # requestor
        'E': 20,  # region
        'F': 20,  # district
        'G': 20,  # community
        'H': 25,  # consultant
        'I': 25,  # contractor
        'J': 25,  # package_number
        'K': 20,  # warehouse
    }
    
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Add data validation for project_type
    project_type_dv = DataValidation(
        type="list",
        formula1='"SHEP,COST,SPEC"',
        showDropDown=False,
        allow_blank=False
    )
    project_type_dv.error = "Please select a valid project type: SHEP, COST, or SPEC"
    project_type_dv.errorTitle = "Invalid Project Type"
    project_type_dv.prompt = "Select project type"
    project_type_dv.promptTitle = "Project Type"
    ws.add_data_validation(project_type_dv)
    project_type_dv.add('C2:C1000')
    
    # Get available materials for reference
    materials = list(InventoryItem.objects.values_list('name', flat=True).order_by('name')[:100])
    if materials:
        # Add materials as reference in a separate sheet
        materials_sheet = wb.create_sheet("Materials Reference")
        materials_sheet.cell(row=1, column=1, value="Available Materials").font = Font(bold=True)
        for idx, material in enumerate(materials, 2):
            materials_sheet.cell(row=idx, column=1, value=material)
        materials_sheet.column_dimensions['A'].width = 40
    
    # Get available warehouses for reference
    warehouses = list(Warehouse.objects.values_list('name', flat=True).order_by('name'))
    if warehouses:
        if 'Materials Reference' in wb.sheetnames:
            ref_sheet = wb['Materials Reference']
        else:
            ref_sheet = wb.create_sheet("Reference")
        
        ref_sheet.cell(row=1, column=3, value="Available Warehouses").font = Font(bold=True)
        for idx, warehouse in enumerate(warehouses, 2):
            ref_sheet.cell(row=idx, column=3, value=warehouse)
        ref_sheet.column_dimensions['C'].width = 30
    
    # Add regions/districts/communities reference
    regions = SHEPCommunity.objects.filter(is_active=True).values('region', 'region_abbr').distinct().order_by('region')[:50]
    if regions:
        if 'Materials Reference' in wb.sheetnames:
            ref_sheet = wb['Materials Reference']
        else:
            ref_sheet = wb.create_sheet("Reference")
        
        ref_sheet.cell(row=1, column=5, value="Regions (Abbreviation)").font = Font(bold=True)
        for idx, r in enumerate(regions, 2):
            ref_sheet.cell(row=idx, column=5, value=f"{r['region']} ({r['region_abbr']})")
        ref_sheet.column_dimensions['E'].width = 35
    
    # Add instructions sheet
    instructions_sheet = wb.create_sheet("Instructions")
    instructions = [
        "BULK MATERIAL REQUEST TEMPLATE - INSTRUCTIONS",
        "",
        "REQUIRED FIELDS:",
        "• name: Material name (must match inventory exactly)",
        "• quantity: Numeric quantity requested",
        "• project_type: SHEP, COST, or SPEC",
        "• requestor: Person/factory/institute making the request (required for COST/SPEC)",
        "• region: Project region",
        "• district: Project district",
        "• community: Project community",
        "",
        "OPTIONAL FIELDS:",
        "• consultant: Project consultant",
        "• contractor: Project contractor",
        "• package_number: Required for SHEP, auto-generated for COST/SPEC",
        "• warehouse: Target warehouse",
        "",
        "PROJECT TYPES:",
        "• SHEP: Regular SHEP project - select package from dropdown",
        "• COST: Cost-sharing project - package auto-generated as COST-[DIST]-[COMM]-[REQ]-[RANDOM]",
        "• SPEC: Special/other project - package auto-generated as SPEC-[DIST]-[COMM]-[REQ]-[RANDOM]",
        "",
        "NOTES:",
        "• Reference the 'Materials Reference' sheet for valid material names",
        "• Abbreviations are shown in parentheses for regions/districts/communities",
    ]
    
    for idx, instruction in enumerate(instructions, 1):
        cell = instructions_sheet.cell(row=idx, column=1, value=instruction)
        if idx == 1:
            cell.font = Font(bold=True, size=14)
        elif instruction.endswith(':'):
            cell.font = Font(bold=True)
    
    instructions_sheet.column_dimensions['A'].width = 80
    
    # Add example row
    example_data = [
        'Cement Bag 50kg',
        100,
        'SHEP',
        'John Doe',
        'Greater Accra',
        'Accra Metropolitan',
        'Osu',
        'ABC Consulting',
        'XYZ Construction',
        'SHEP-PKG-001',
        'Main Warehouse'
    ]
    for col_idx, value in enumerate(example_data, 1):
        ws.cell(row=2, column=col_idx, value=value)
    
    # Create response
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="material_request_template.xlsx"'
    
    return response


def download_shep_community_template(request):
    """
    Generate and download an Excel template for bulk SHEP community import.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return HttpResponse(
            "Required package openpyxl not installed.",
            status=500
        )
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "SHEP Communities"
    
    # Define headers
    headers = ['region', 'district', 'community', 'package_number']
    
    # Style headers
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Add example row
    example_data = ['Greater Accra', 'Accra Metropolitan', 'Osu', 'SHEP-PKG-001']
    for col_idx, value in enumerate(example_data, 1):
        ws.cell(row=2, column=col_idx, value=value)
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 20
    
    # Add instructions sheet
    instructions_ws = wb.create_sheet(title="Instructions")
    instructions = [
        "SHEP Community Bulk Upload Instructions",
        "",
        "Required Columns:",
        "- region: The region name (e.g., 'Greater Accra')",
        "- district: The district name (e.g., 'Accra Metropolitan')",
        "- community: The community name (e.g., 'Osu')",  
        "- package_number: The SHEP package number (e.g., 'SHEP-PKG-001')",
        "",
        "Notes:",
        "- Abbreviations will be auto-generated from the names",
        "- Duplicate entries (same region+district+community) will be skipped",
        "- All fields are required",
    ]
    
    for row_idx, text in enumerate(instructions, 1):
        cell = instructions_ws.cell(row=row_idx, column=1, value=text)
        if row_idx == 1:
            cell.font = Font(bold=True, size=14)
    
    instructions_ws.column_dimensions['A'].width = 60
    
    # Create response
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="shep_community_template.xlsx"'
    
    return response


def upload_shep_communities(request):
    """
    Process bulk SHEP community upload from Excel file.
    """
    from django.shortcuts import render, redirect
    from django.contrib.auth.decorators import login_required, user_passes_test
    
    if not request.user.is_superuser:
        messages.error(request, "You don't have permission to upload communities.")
        return redirect('shep_community_list')
    
    if request.method != 'POST':
        return redirect('shep_community_list')
    
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect('shep_community_list')
    
    # Check file extension
    if not uploaded_file.name.endswith(('.xlsx', '.xls')):
        messages.error(request, "Please upload an Excel file (.xlsx or .xls).")
        return redirect('shep_community_list')
    
    try:
        import pandas as pd
    except ImportError:
        messages.error(request, "Required package pandas not installed.")
        return redirect('shep_community_list')
    
    try:
        # Read Excel file
        df = pd.read_excel(uploaded_file)
        
        # Required columns
        required_columns = ['region', 'district', 'community', 'package_number']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
            return redirect('shep_community_list')
        
        # Process each row
        created_count = 0
        skipped_count = 0
        error_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                region = str(row['region']).strip()
                district = str(row['district']).strip()
                community_name = str(row['community']).strip()
                package_number = str(row['package_number']).strip()
                
                # Skip empty rows
                if not region or not district or not community_name or region == 'nan':
                    continue
                
                # Check for existing entry
                existing = SHEPCommunity.objects.filter(
                    region=region,
                    district=district,
                    community=community_name
                ).exists()
                
                if existing:
                    skipped_count += 1
                    continue
                
                # Create new community (abbreviations auto-generated by model's save method)
                SHEPCommunity.objects.create(
                    region=region,
                    district=district,
                    community=community_name,
                    package_number=package_number
                )
                created_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        # Build success/error message
        msg_parts = []
        if created_count > 0:
            msg_parts.append(f"{created_count} communities created")
        if skipped_count > 0:
            msg_parts.append(f"{skipped_count} duplicates skipped")
        if error_count > 0:
            msg_parts.append(f"{error_count} errors")
        
        if created_count > 0:
            messages.success(request, ", ".join(msg_parts) + ".")
        elif skipped_count > 0:
            messages.warning(request, ", ".join(msg_parts) + ".")
        else:
            messages.error(request, "No communities were created. " + ", ".join(msg_parts))
        
        if errors:
            for error in errors[:5]:  # Show first 5 errors
                messages.warning(request, error)
            if len(errors) > 5:
                messages.warning(request, f"... and {len(errors) - 5} more errors.")
        
    except Exception as e:
        messages.error(request, f"Error processing file: {str(e)}")
    
    return redirect('shep_community_list')
