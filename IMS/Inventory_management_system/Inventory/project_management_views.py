# Inventory/project_management_views.py
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count, Q, F, Avg, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from .models import BillOfQuantity, Project, ProjectSite, Community
from .utils import is_superuser, is_store_officer, is_management
from collections import defaultdict
import json
import logging

logger = logging.getLogger(__name__)


def get_user_accessible_projects(user):
    """
    Get projects that a user can access based on their role and assignments.

    Access rules:
    - Superusers: All projects
    - Project managers: Own managed projects
    - Management group: All projects (can view overall metrics)
    - Store officers: Projects where they're assigned as site supervisors

    Returns: Q object for filtering BoQ items
    """
    if is_superuser(user):
        # Superusers see all data
        return Q()

    if is_management(user):
        # Management can see all projects
        return Q()

    # Build a Q object for non-management users
    accessible_projects = Q()

    # Add projects where user is project manager
    managed_projects = Project.objects.filter(project_manager=user).values_list('phase', flat=True).distinct()
    if managed_projects:
        accessible_projects |= Q(phase__in=managed_projects)

    # Add projects where user is site supervisor (through ProjectSite)
    supervised_sites = ProjectSite.objects.filter(site_supervisor=user).values_list(
        'project__phase', flat=True
    ).distinct()
    if supervised_sites:
        accessible_projects |= Q(phase__in=supervised_sites)

    # If no access, return empty Q (user sees nothing)
    return accessible_projects if accessible_projects else Q(id__isnull=True)


def _norm_pkg(p):
    """Normalize a package number for matching across BoQ and Community
    (strip, collapse internal whitespace, upper-case)."""
    return ' '.join((p or '').strip().upper().split())


def _boq_package_totals(boq_qs):
    """Aggregate a BoQ queryset into per-package totals keyed by normalized
    package number. BoQ has no community, so community-level figures are built
    by joining a Community's package_number(s) to these package totals.

    Returns: { norm_package: {contract, received, items, contractors:set} }
    """
    totals = defaultdict(lambda: {'contract': 0.0, 'received': 0.0,
                                  'items': 0, 'contractors': set()})
    for b in boq_qs.values('package_number', 'contract_quantity',
                           'quantity_received', 'contractor'):
        key = _norm_pkg(b['package_number'])
        if not key:
            continue
        t = totals[key]
        t['contract'] += b['contract_quantity'] or 0
        t['received'] += b['quantity_received'] or 0
        t['items'] += 1
        c = (b['contractor'] or '').strip()
        if c:
            t['contractors'].add(c)
    return totals


def _community_works_map():
    """Highest works progress per (region, district, community), lower-cased,
    from ProjectSite — the 5-stage works completion source."""
    works_map = {}
    for s in ProjectSite.objects.values('region', 'district', 'community',
                                         'progress_percent', 'works_status'):
        key = ((s['region'] or '').lower(), (s['district'] or '').lower(),
               (s['community'] or '').lower())
        if key not in works_map or (s['progress_percent'] or 0) > (works_map[key]['progress_percent'] or 0):
            works_map[key] = s
    return works_map


def _group_communities_by_packages(community_qs):
    """Group a Community queryset into {(region, district, community): {norm_pkgs}}.
    Communities without a name are skipped; packages are normalized."""
    grouped = {}
    for c in community_qs.values('region', 'district', 'community', 'package_number'):
        key = (c['region'] or '', c['district'] or '', c['community'] or '')
        if not key[2]:
            continue
        pkgs = grouped.setdefault(key, set())
        pk = _norm_pkg(c['package_number'])
        if pk:
            pkgs.add(pk)
    return grouped


class ProjectManagementDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    High-level project management dashboard for Bill of Quantities.
    Provides executive overview with graphs and community completion summaries.
    Accessible to Management group and superusers only.
    """
    template_name = 'Inventory/project_management_dashboard.html'
    
    def test_func(self):
        """Allow access to Management, store operations users, and superusers"""
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get BOQ items that user can access (project segregation)
            access_filter = get_user_accessible_projects(self.request.user)
            boq_items = BillOfQuantity.objects.filter(access_filter)
            
            # Overall statistics
            total_items = boq_items.count()
            total_communities = boq_items.values('community').distinct().count()
            total_packages = boq_items.values('package_number').distinct().count()
            total_regions = boq_items.values('region').distinct().count()
            total_districts = boq_items.values('district').distinct().count()
            
            # Calculate overall contract quantity and received quantity
            overall_stats = boq_items.aggregate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0)
            )
            
            total_contract = float(overall_stats['total_contract'])
            total_received = float(overall_stats['total_received'])
            overall_completion = (total_received / total_contract * 100) if total_contract > 0 else 0
            
            # Community-level aggregation
            community_data = boq_items.values('community', 'region', 'district', 'phase').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0),
                item_count=Count('id'),
                package_count=Count('package_number', distinct=True)
            ).order_by('-total_contract')
            
            # Calculate completion percentage for each community
            community_list = []
            community_chart_labels = []
            community_chart_data = []
            
            for comm in community_data:
                if comm['community']:  # Skip null communities
                    completion = (comm['total_received'] / comm['total_contract'] * 100) if comm['total_contract'] > 0 else 0
                    community_list.append({
                        'name': comm['community'],
                        'region': comm['region'],
                        'district': comm['district'],
                        'phase': comm['phase'],
                        'total_contract': comm['total_contract'],
                        'total_received': comm['total_received'],
                        'completion': round(completion, 2),
                        'item_count': comm['item_count'],
                        'package_count': comm['package_count'],
                        'status': 'Complete' if completion >= 100 else 'In Progress' if completion > 0 else 'Not Started'
                    })
                    
                    # Top 10 communities for chart
                    if len(community_chart_labels) < 10:
                        community_chart_labels.append(comm['community'] or 'Unknown')
                        community_chart_data.append(round(completion, 2))
            
            # Package-level aggregation
            package_data = boq_items.values('package_number', 'contractor', 'consultant', 'phase').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0),
                item_count=Count('id'),
                community_count=Count('community', distinct=True)
            ).order_by('-total_contract')
            
            # Calculate completion for packages
            package_list = []
            package_chart_labels = []
            package_chart_data = []
            
            for pkg in package_data:
                if pkg['package_number']:
                    completion = (pkg['total_received'] / pkg['total_contract'] * 100) if pkg['total_contract'] > 0 else 0
                    package_list.append({
                        'number': pkg['package_number'],
                        'contractor': pkg['contractor'],
                        'consultant': pkg['consultant'],
                        'phase': pkg['phase'],
                        'total_contract': pkg['total_contract'],
                        'total_received': pkg['total_received'],
                        'completion': round(completion, 2),
                        'item_count': pkg['item_count'],
                        'community_count': pkg['community_count']
                    })
                    
                    # Top 10 packages for chart
                    if len(package_chart_labels) < 10:
                        package_chart_labels.append(pkg['package_number'])
                        package_chart_data.append(round(completion, 2))
            
            # Material-level aggregation (top materials by quantity)
            material_data = boq_items.values('material_description', 'item_code').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0)
            ).order_by('-total_contract')[:15]  # Top 15 materials
            
            material_chart_labels = []
            material_contract_data = []
            material_received_data = []
            
            for mat in material_data:
                material_chart_labels.append(mat['material_description'][:30] + '...' if len(mat['material_description']) > 30 else mat['material_description'])
                material_contract_data.append(float(mat['total_contract']))
                material_received_data.append(float(mat['total_received']))
            
            # Completion status breakdown
            completed_count = sum(1 for c in community_list if c['completion'] >= 100)
            in_progress_count = sum(1 for c in community_list if 0 < c['completion'] < 100)
            not_started_count = sum(1 for c in community_list if c['completion'] == 0)

            # Project-type segregation — the dashboard's whole point. Every
            # tile is rolled up per project_type so SHEP, Cost Sharing,
            # Streetlights, Turnkey, etc. are each visible as a standalone
            # column instead of being averaged into one number.
            #
            # The chart deliberately does NOT repeat the Contract-vs-Received
            # data the tiles already show. It instead surfaces two things
            # the BoQ alone can answer that aren't visible anywhere else:
            #   (a) community-completion buckets per project type — where
            #       work is stuck (Not Started / In Progress / Completed)
            #   (b) over-issued line counts per project type — the leading
            #       indicator of contract / drawdown trouble.
            type_rows = boq_items.values('project_type').annotate(
                items=Count('id'),
                communities=Count('community', distinct=True),
                packages=Count('package_number', distinct=True),
                contract=Coalesce(Sum('contract_quantity'), 0.0),
                received=Coalesce(Sum('quantity_received'), 0.0),
            ).order_by('project_type')

            # Pre-bucket communities per project type once so we don't run
            # one query per type per bucket.
            per_type_comm = {}
            comm_rows = boq_items.values('project_type', 'community').annotate(
                contract=Coalesce(Sum('contract_quantity'), 0.0),
                received=Coalesce(Sum('quantity_received'), 0.0),
            )
            for r in comm_rows:
                if not r['community']: continue
                pt = r['project_type'] or 'Unassigned'
                c = float(r['contract'] or 0)
                rcv = float(r['received'] or 0)
                completion = (rcv / c * 100) if c > 0 else 0
                bucket = 'completed' if completion >= 100 else ('in_progress' if completion > 0 else 'not_started')
                d = per_type_comm.setdefault(pt, {'completed': 0, 'in_progress': 0, 'not_started': 0})
                d[bucket] += 1

            # Over-issued line counts per project type (received > contract).
            over_issued = {}
            for r in boq_items.values('project_type').annotate(
                n=Count('id', filter=Q(quantity_received__gt=F('contract_quantity'))),
            ):
                over_issued[r['project_type'] or 'Unassigned'] = r['n']

            project_segments = []
            for row in type_rows:
                pt = row['project_type'] or 'Unassigned'
                contract = float(row['contract'] or 0)
                received = float(row['received'] or 0)
                project_segments.append({
                    'project_type': pt,
                    'items': row['items'],
                    'communities': row['communities'],
                    'packages': row['packages'],
                    'contract_quantity': contract,
                    'received_quantity': received,
                    'completion': round((received / contract * 100) if contract > 0 else 0, 2),
                    'over_issued_lines': over_issued.get(pt, 0),
                    'communities_completed': per_type_comm.get(pt, {}).get('completed', 0),
                    'communities_in_progress': per_type_comm.get(pt, {}).get('in_progress', 0),
                    'communities_not_started': per_type_comm.get(pt, {}).get('not_started', 0),
                })
            project_segments_json = json.dumps({
                'labels': [s['project_type'] for s in project_segments],
                'completed': [s['communities_completed'] for s in project_segments],
                'in_progress': [s['communities_in_progress'] for s in project_segments],
                'not_started': [s['communities_not_started'] for s in project_segments],
                'over_issued_lines': [s['over_issued_lines'] for s in project_segments],
            })

            # Add all data to context
            context.update({
                'total_items': total_items,
                'total_communities': total_communities,
                'total_packages': total_packages,
                'total_regions': total_regions,
                'total_districts': total_districts,
                'total_contract': total_contract,
                'total_received': total_received,
                'overall_completion': round(overall_completion, 2),
                'community_list': community_list,
                'package_list': package_list,
                'completed_count': completed_count,
                'in_progress_count': in_progress_count,
                'not_started_count': not_started_count,
                'project_segments': project_segments,
                'project_segments_json': project_segments_json,
                # Chart data as JSON for JavaScript
                'community_chart_labels': json.dumps(community_chart_labels),
                'community_chart_data': json.dumps(community_chart_data),
                'package_chart_labels': json.dumps(package_chart_labels),
                'package_chart_data': json.dumps(package_chart_data),
                'material_chart_labels': json.dumps(material_chart_labels),
                'material_contract_data': json.dumps(material_contract_data),
                'material_received_data': json.dumps(material_received_data),
            })
            
            logger.info(f"Project management dashboard loaded successfully with {total_items} BOQ items")
            
        except Exception as e:
            logger.error(f"Error loading project management dashboard: {str(e)}", exc_info=True)
            context.update({
                'error': f"Error loading dashboard data: {str(e)}",
                'total_items': 0,
                'total_communities': 0,
                'total_packages': 0,
                'community_list': [],
                'package_list': [],
            })
        
        return context


class CommunityAnalysisView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Detailed community-level analysis with full data table and expanded visualizations.
    """
    template_name = 'Inventory/project_community_analysis.html'
    
    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Community is the spine. Material totals come from BoQ joined to
            # each community's package_number(s); completion here is material
            # delivery (received / contract), matching this page's original
            # intent. Works-stage % lives on the Community Progress page.
            access_filter = get_user_accessible_projects(self.request.user)
            pkg_tot = _boq_package_totals(BillOfQuantity.objects.filter(access_filter))
            grouped = _group_communities_by_packages(Community.objects.filter(is_active=True))

            community_list = []
            chart_rows = []
            completed_count = 0
            in_progress_count = 0
            not_started_count = 0

            for (region, district, community), pkgs in grouped.items():
                contract = received = items = 0
                for p in pkgs:
                    t = pkg_tot.get(p)
                    if t:
                        contract += t['contract']
                        received += t['received']
                        items += t['items']
                completion = (received / contract * 100) if contract > 0 else 0
                status = 'Complete' if completion >= 100 else 'In Progress' if completion > 0 else 'Not Started'

                if status == 'Complete':
                    completed_count += 1
                elif status == 'In Progress':
                    in_progress_count += 1
                else:
                    not_started_count += 1

                community_list.append({
                    'name': community,
                    'region': region,
                    'district': district,
                    'phase': '',
                    'total_contract': contract,
                    'total_received': received,
                    'balance': contract - received,
                    'completion': round(completion, 2),
                    'item_count': items,
                    'package_count': len(pkgs),
                    'status': status,
                })
                if contract > 0:
                    chart_rows.append((community or 'Unknown', round(completion, 2)))

            community_list.sort(key=lambda c: (c['region'], c['district'], c['name']))

            # Chart: only communities with BoQ material data, capped so the
            # canvas stays readable (3k+ communities would be unusable).
            chart_rows.sort(key=lambda r: r[1], reverse=True)
            chart_rows = chart_rows[:50]
            chart_labels = [r[0] for r in chart_rows]
            chart_data = [r[1] for r in chart_rows]

            context.update({
                'community_list': community_list,
                'total_communities': len(community_list),
                'completed_count': completed_count,
                'in_progress_count': in_progress_count,
                'not_started_count': not_started_count,
                'chart_labels': json.dumps(chart_labels),
                'chart_data': json.dumps(chart_data),
                'title': 'Community Analysis'
            })
            
        except Exception as e:
            logger.error(f"Error loading community analysis: {str(e)}", exc_info=True)
            context['error'] = str(e)
        
        return context


class PackageAnalysisView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Detailed package-level analysis with full data table and expanded visualizations.
    """
    template_name = 'Inventory/project_package_analysis.html'
    
    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get BOQ items that user can access (project segregation)
            access_filter = get_user_accessible_projects(self.request.user)
            boq_items = BillOfQuantity.objects.filter(access_filter)

            # Package-level aggregation with full data
            package_data = boq_items.values('package_number', 'contractor', 'consultant', 'region', 'phase').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0),
                item_count=Count('id'),
                community_count=Count('community', distinct=True)
            ).order_by('package_number')
            
            # Process all packages
            package_list = []
            chart_labels = []
            chart_data = []
            
            for pkg in package_data:
                if pkg['package_number']:
                    completion = (pkg['total_received'] / pkg['total_contract'] * 100) if pkg['total_contract'] > 0 else 0
                    package_list.append({
                        'number': pkg['package_number'],
                        'contractor': pkg['contractor'],
                        'consultant': pkg['consultant'],
                        'region': pkg['region'],
                        'phase': pkg['phase'],
                        'total_contract': pkg['total_contract'],
                        'total_received': pkg['total_received'],
                        'balance': pkg['total_contract'] - pkg['total_received'],
                        'completion': round(completion, 2),
                        'item_count': pkg['item_count'],
                        'community_count': pkg['community_count'],
                        'status': 'Complete' if completion >= 100 else 'In Progress' if completion > 0 else 'Not Started'
                    })
                    chart_labels.append(pkg['package_number'])
                    chart_data.append(round(completion, 2))
            
            context.update({
                'package_list': package_list,
                'total_packages': len(package_list),
                'chart_labels': json.dumps(chart_labels),
                'chart_data': json.dumps(chart_data),
                'title': 'Package Analysis'
            })
            
        except Exception as e:
            logger.error(f"Error loading package analysis: {str(e)}", exc_info=True)
            context['error'] = str(e)
        
        return context


class MaterialAnalysisView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Detailed material-level analysis with full data table and expanded visualizations.
    """
    template_name = 'Inventory/project_material_analysis.html'
    
    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get BOQ items that user can access (project segregation)
            access_filter = get_user_accessible_projects(self.request.user)
            boq_items = BillOfQuantity.objects.filter(access_filter)

            # Material-level aggregation with full data
            material_data = boq_items.values('material_description', 'item_code').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0),
                usage_count=Count('id')
            ).order_by('-total_contract')
            
            # Process all materials
            material_list = []
            chart_labels = []
            contract_data = []
            received_data = []
            
            for mat in material_data:
                completion = (mat['total_received'] / mat['total_contract'] * 100) if mat['total_contract'] > 0 else 0
                material_list.append({
                    'description': mat['material_description'],
                    'code': mat['item_code'],
                    'total_contract': mat['total_contract'],
                    'total_received': mat['total_received'],
                    'balance': mat['total_contract'] - mat['total_received'],
                    'completion': round(completion, 2),
                    'usage_count': mat['usage_count'],
                    'status': 'Complete' if completion >= 100 else 'In Progress' if completion > 0 else 'Not Started'
                })
                
                # Add to chart (limit to top 30 for readability)
                if len(chart_labels) < 30:
                    desc = mat['material_description']
                    chart_labels.append(desc[:30] + '...' if len(desc) > 30 else desc)
                    contract_data.append(float(mat['total_contract']))
                    received_data.append(float(mat['total_received']))
            
            context.update({
                'material_list': material_list,
                'total_materials': len(material_list),
                'chart_labels': json.dumps(chart_labels),
                'contract_data': json.dumps(contract_data),
                'received_data': json.dumps(received_data),
                'title': 'Material Analysis'
            })
            
        except Exception as e:
            logger.error(f"Error loading material analysis: {str(e)}", exc_info=True)
            context['error'] = str(e)

        return context


# ---------------------------------------------------------------------------
# Community Progress (standalone breakdown page)
# ---------------------------------------------------------------------------
#
# A dedicated "Community Progress" list page with an Actions column. Each row
# has an "Expand" button that opens a per-community breakdown page showing the
# full SHEP works sheet: HT/LV poles + transformers (contract, supplied,
# planted, dressed, strung, commissioned), customer-service connections, and
# the HT / LV / Substation / Overall completion flags.
#
# Data sources (per the spec):
#   * Bill of Quantity  -> contract & supplied quantities, region, district,
#                          community, package, contractor, consultant, phase.
#   * Site Progress form -> the on-the-ground works figures captured on
#                          ProjectSite (poles erected, conductor strung,
#                          transformers installed/commissioned, meters
#                          connected, % complete, works status, notes).
#
# The site-progress form currently records combined poles (not split by HT/LV)
# and does not track the planted/dressed lifecycle per pole class, so those
# specific cells render as "—" (not yet captured at that granularity). Every
# column the sheet asks for is present so the page is ready to surface richer
# works data the moment the model captures it.

def _boq_class(boq):
    """Bucket a BoQ row into 'ht'/'lv'/'transformer' (or None), preferring the
    explicit ``voltage_class`` and only falling back to the description
    heuristic when it's blank."""
    vc = (getattr(boq, 'voltage_class', '') or '').upper()
    mapped = {'HT': 'ht', 'LV': 'lv', 'XFMR': 'transformer'}.get(vc)
    if mapped:
        return mapped
    if vc == 'METER':
        return None  # meters are tracked via site connections, not HT/LV/xfmr
    return _categorise_boq_material(boq.material_description)


def _categorise_boq_material(description):
    """Bucket a BoQ material description into 'ht', 'lv', 'transformer' or None.

    Heuristic keyword match against the free-text material description, since
    BoQ rows aren't otherwise typed. Order matters: transformer is checked
    first, then the HT/LV qualifiers, then a generic pole fallback (treated
    as LV, the common case for SHEP reticulation). Now only used as the
    fallback when a BoQ row has no explicit ``voltage_class`` (see _boq_class).
    """
    if not description:
        return None
    d = description.lower()
    if 'transformer' in d or 'xfmr' in d:
        return 'transformer'
    is_pole = 'pole' in d
    is_ht = any(k in d for k in ('h.t', 'ht ', 'high tension', 'high voltage',
                                 'hv ', '11kv', '33kv', 'primary'))
    is_lv = any(k in d for k in ('l.v', 'lv ', 'low tension', 'low voltage',
                                 'secondary', '415v', '400v', '0.4kv'))
    if is_pole or is_ht or is_lv:
        if is_ht and not is_lv:
            return 'ht'
        if is_lv and not is_ht:
            return 'lv'
        # Ambiguous / generic pole -> default to LV reticulation.
        return 'lv'
    return None


def _site_progress_for_community(region, district, community):
    """Aggregate Site-Progress works figures for one community.

    Sums the cumulative works counters across every ProjectSite that matches
    the community (case-insensitive on region/district/community) and returns
    a plain dict the template can read. Returns zeros when no site matches.
    """
    from types import SimpleNamespace
    from .services.community_progress import compute_site_completion
    from .models import Community as CommunityModel

    sites = ProjectSite.objects.filter(
        region__iexact=region or '',
        district__iexact=district or '',
        community__iexact=community or '',
    )
    agg = sites.aggregate(
        ht_erected=Coalesce(Sum('ht_poles_erected'), 0),
        ht_dressed=Coalesce(Sum('ht_poles_dressed'), 0),
        ht_strung=Coalesce(Sum('ht_poles_strung'), 0),
        lv_erected=Coalesce(Sum('lv_poles_erected'), 0),
        lv_dressed=Coalesce(Sum('lv_poles_dressed'), 0),
        lv_strung=Coalesce(Sum('lv_poles_strung'), 0),
        ht_conductor_m=Coalesce(Sum('ht_conductor_strung_m'), 0.0, output_field=FloatField()),
        lv_conductor_m=Coalesce(Sum('lv_conductor_strung_m'), 0.0, output_field=FloatField()),
        transformers_installed=Coalesce(Sum('transformers_installed'), 0),
        transformers_commissioned=Coalesce(Sum('transformers_commissioned'), 0),
        cs_1ph=Coalesce(Sum('meters_1ph_installed'), 0),
        cs_3ph=Coalesce(Sum('meters_3ph_installed'), 0),
        site_count=Count('id'),
    )
    # Legacy combined values, kept for any remaining readers.
    agg['poles_planted'] = (agg['ht_erected'] or 0) + (agg['lv_erected'] or 0)
    agg['conductor_strung_m'] = (agg['ht_conductor_m'] or 0) + (agg['lv_conductor_m'] or 0)

    # 5-stage completion vs the community's frozen (BoQ-seeded) targets.
    targets = CommunityModel.objects.filter(
        region__iexact=region or '', district__iexact=district or '',
        community__iexact=community or '', is_active=True,
    ).first()
    synthetic = SimpleNamespace(
        region=region, district=district, community=community,
        ht_poles_erected=agg['ht_erected'], ht_poles_dressed=agg['ht_dressed'], ht_poles_strung=agg['ht_strung'],
        lv_poles_erected=agg['lv_erected'], lv_poles_dressed=agg['lv_dressed'], lv_poles_strung=agg['lv_strung'],
        transformers_installed=agg['transformers_installed'],
        transformers_commissioned=agg['transformers_commissioned'],
        meters_1ph_installed=agg['cs_1ph'], meters_3ph_installed=agg['cs_3ph'],
    )
    completion = compute_site_completion(synthetic, community=targets)
    agg['completion'] = completion
    agg['stages'] = completion['stages']
    agg['avg_progress'] = completion['percent']
    agg['targets'] = targets
    agg['has_targets'] = completion['has_targets']

    latest = sites.order_by('-progress_updated_at', '-updated_at').first()
    agg['works_status'] = latest.get_works_status_display() if latest else '—'
    agg['remarks'] = (latest.progress_notes if latest and latest.progress_notes else '')
    return agg


class CommunityProgressListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Standalone community-progress list with an Expand action per community.

    One row per (region, district, community). The Expand button links to the
    detailed breakdown page for that community.
    """
    template_name = 'Inventory/community_progress_list.html'

    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            # Community is the spine: list every active community, attach its
            # works % from ProjectSite, and its material totals from BoQ joined
            # by package_number (BoQ itself carries no community).
            access_filter = get_user_accessible_projects(self.request.user)
            pkg_tot = _boq_package_totals(BillOfQuantity.objects.filter(access_filter))

            q = (self.request.GET.get('q') or '').strip()
            region_f = (self.request.GET.get('region') or '').strip()

            comms = Community.objects.filter(is_active=True)
            if q:
                comms = comms.filter(
                    Q(community__icontains=q) | Q(district__icontains=q)
                    | Q(region__icontains=q) | Q(package_number__icontains=q)
                )
            if region_f:
                comms = comms.filter(region=region_f)

            works_map = _community_works_map()
            grouped = _group_communities_by_packages(comms)

            community_list = []
            for (region, district, community), pkgs in grouped.items():
                contract = received = items = 0
                contractors = set()
                for p in pkgs:
                    t = pkg_tot.get(p)
                    if t:
                        contract += t['contract']
                        received += t['received']
                        items += t['items']
                        contractors |= t['contractors']
                material_completion = round((received / contract * 100), 1) if contract > 0 else 0

                works = works_map.get((region.lower(), district.lower(), community.lower()))
                completion = (works['progress_percent'] or 0) if works else 0
                status = ('Complete' if completion >= 100
                          else 'In Progress' if completion > 0 else 'Not Started')
                community_list.append({
                    'community': community,
                    'region': region,
                    'district': district,
                    'package_count': len(pkgs),
                    'contractor_count': len(contractors),
                    'item_count': items,
                    'total_contract': contract,
                    'total_received': received,
                    'completion': completion,            # works-based (5-stage)
                    'material_completion': material_completion,  # BoQ delivery
                    'status': status,
                })
            community_list.sort(key=lambda c: (c['region'], c['district'], c['community']))

            regions = list(
                Community.objects.filter(is_active=True).exclude(region='')
                .values_list('region', flat=True).distinct().order_by('region')
            )

            context.update({
                'community_list': community_list,
                'total_communities': len(community_list),
                'complete_count': sum(1 for c in community_list if c['status'] == 'Complete'),
                'in_progress_count': sum(1 for c in community_list if c['status'] == 'In Progress'),
                'not_started_count': sum(1 for c in community_list if c['status'] == 'Not Started'),
                'regions': regions,
                'filters': {'q': q, 'region': region_f},
                'title': 'Community Progress',
            })
        except Exception as e:
            logger.error(f"Error loading community progress list: {str(e)}", exc_info=True)
            context['error'] = str(e)
        return context


class CommunityProgressBreakdownView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Per-community works breakdown opened from the Expand button.

    Renders the full SHEP sheet: one row per package within the community,
    with HT/LV pole and transformer contract & supplied figures from the BoQ,
    plus the community-level site-progress works figures (planted, strung,
    dressed, commissioned, connections, completion) from the Site Progress form.
    The community is identified by the region/district/community query params.
    """
    template_name = 'Inventory/community_progress_breakdown.html'

    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            region = (self.request.GET.get('region') or '').strip()
            district = (self.request.GET.get('district') or '').strip()
            community = (self.request.GET.get('community') or '').strip()

            access_filter = get_user_accessible_projects(self.request.user)
            boq_all = BillOfQuantity.objects.filter(access_filter)

            # BoQ carries no community, so resolve this community's package
            # number(s) from the Community model and match BoQ by package.
            # Keep the legacy community-text match as a fallback for any data
            # that does carry a community.
            comm_pkgs_norm = {
                _norm_pkg(p) for p in Community.objects.filter(
                    region__iexact=region, district__iexact=district,
                    community__iexact=community,
                ).values_list('package_number', flat=True) if _norm_pkg(p)
            }
            raw_match = [
                pn for pn in boq_all.values_list('package_number', flat=True).distinct()
                if _norm_pkg(pn) in comm_pkgs_norm
            ]
            items = boq_all.filter(
                Q(package_number__in=raw_match)
                | Q(region__iexact=region, district__iexact=district,
                    community__iexact=community)
            )

            # Group the BoQ rows by package (each package may have its own
            # contractor / consultant), then categorise each item into HT / LV
            # / transformer and accumulate contract vs supplied.
            packages = {}
            for it in items:
                key = it.package_number or '—'
                pkg = packages.setdefault(key, {
                    'package_number': key,
                    'contractor': it.contractor,
                    'consultant': it.consultant,
                    'phase': it.phase,
                    'ht': {'contract': 0.0, 'supplied': 0.0},
                    'lv': {'contract': 0.0, 'supplied': 0.0},
                    'transformer': {'contract': 0.0, 'supplied': 0.0},
                })
                # The HT/LV columns are specifically *pole* counts, so only
                # pole lines feed them — conductor (also HT/LV) must not be
                # added to a pole contract figure. Transformers feed their own
                # column. Conductor and meters are reported elsewhere.
                from .services.community_progress import _kind
                cat = _boq_class(it)
                kind = _kind(it.material_description, it.item_code)
                if cat == 'transformer' or kind == 'transformer':
                    bucket = 'transformer'
                elif cat in ('ht', 'lv') and kind == 'pole':
                    bucket = cat
                else:
                    bucket = None
                if bucket:
                    pkg[bucket]['contract'] += it.contract_quantity or 0
                    pkg[bucket]['supplied'] += it.quantity_received or 0

            # Completion flags per package are material-completeness proxies:
            # supplied >= contract for that class (only when a contract exists).
            def _complete(group):
                return group['contract'] > 0 and group['supplied'] >= group['contract']

            package_rows = []
            for key in sorted(packages.keys()):
                pkg = packages[key]
                pkg['ht_complete'] = _complete(pkg['ht'])
                pkg['lv_complete'] = _complete(pkg['lv'])
                pkg['substation_complete'] = _complete(pkg['transformer'])
                pkg['overall_complete'] = (
                    pkg['ht_complete'] and pkg['lv_complete'] and pkg['substation_complete']
                )
                package_rows.append(pkg)

            site = _site_progress_for_community(region, district, community)

            # Community-level contract/supplied totals across all classes.
            totals = {
                'ht': {'contract': sum(p['ht']['contract'] for p in package_rows),
                       'supplied': sum(p['ht']['supplied'] for p in package_rows)},
                'lv': {'contract': sum(p['lv']['contract'] for p in package_rows),
                       'supplied': sum(p['lv']['supplied'] for p in package_rows)},
                'transformer': {'contract': sum(p['transformer']['contract'] for p in package_rows),
                                'supplied': sum(p['transformer']['supplied'] for p in package_rows)},
            }

            context.update({
                'region': region,
                'district': district,
                'community': community,
                'package_rows': package_rows,
                'totals': totals,
                'site': site,
                'has_data': bool(package_rows),
                'title': f'Community Progress — {community}',
            })
        except Exception as e:
            logger.error(f"Error loading community breakdown: {str(e)}", exc_info=True)
            context['error'] = str(e)
        return context


class _TargetsPermMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Same access as the progress pages: management / store officer / superuser."""
    def test_func(self):
        user = self.request.user
        return is_management(user) or is_store_officer(user) or is_superuser(user)


class PullTargetsFromBoqView(_TargetsPermMixin, View):
    """POST: copy BoQ contract quantities into one community's frozen targets.

    Duplicate-safe and idempotent — writes only to the canonical community
    record that completion reads from, and SETS (not adds) the values.
    """
    def post(self, request, *args, **kwargs):
        region = (request.POST.get('region') or '').strip()
        district = (request.POST.get('district') or '').strip()
        community = (request.POST.get('community') or '').strip()

        from .services.community_progress import pull_targets_for_location

        if not (region and district and community):
            messages.error(request, "Missing community identity; cannot pull targets.")
            return self._back(region, district, community)

        res = pull_targets_for_location(region, district, community,
                                        user=request.user, apply=True)
        status = res['status']
        if status == 'no_community':
            messages.error(
                request,
                f"No community record found for '{community}' ({district}, {region}). "
                "Import the community first, then pull targets.")
        elif status == 'locked':
            messages.warning(
                request,
                f"Targets for '{community}' are locked (frozen baseline) and were "
                "not overwritten. Unlock the community to re-pull.")
        else:
            changed = sum(1 for d in res['diff'].values() if d['delta'] != 0)
            msg = (f"Pulled BoQ targets for '{community}' "
                   f"({changed} field(s) updated).")
            if res['duplicates'] > 1:
                msg += (f" Note: {res['duplicates']} duplicate community records "
                        "exist for this location — targets were written to the "
                        "canonical one only (no double-counting). Consider merging "
                        "the duplicates.")
            messages.success(request, msg)
        return self._back(region, district, community)

    def _back(self, region, district, community):
        url = reverse('community_progress_breakdown')
        qs = urlencode({'region': region, 'district': district, 'community': community})
        return redirect(f"{url}?{qs}")


class BulkPullTargetsFromBoqView(_TargetsPermMixin, View):
    """POST: pull BoQ targets for every distinct community the user can access.

    De-duplicates locations so a community spanning several packages is pulled
    once. Honours locked communities and reports duplicate records seen.
    """
    def post(self, request, *args, **kwargs):
        from .services.community_progress import bulk_pull_targets

        access_filter = get_user_accessible_projects(request.user)
        boq = BillOfQuantity.objects.filter(access_filter)
        s = bulk_pull_targets(boq, user=request.user)

        parts = [f"{s['pulled']} community target set(s) pulled from BoQ "
                 f"across {s['locations']} location(s)."]
        if s['locked']:
            parts.append(f"{s['locked']} locked and left untouched.")
        if s['no_community']:
            parts.append(f"{s['no_community']} BoQ location(s) had no community record.")
        if s['duplicates_seen']:
            parts.append(f"{s['duplicates_seen']} location(s) had duplicate community "
                         "records — written to the canonical row only.")
        messages.success(request, " ".join(parts))
        return redirect('community_progress_list')
