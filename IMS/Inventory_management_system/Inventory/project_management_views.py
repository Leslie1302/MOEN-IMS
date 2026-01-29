# Inventory/project_management_views.py
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count, Q, F, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from .models import BillOfQuantity
from .utils import is_superuser
import json
import logging

logger = logging.getLogger(__name__)


class ProjectManagementDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    High-level project management dashboard for Bill of Quantities.
    Provides executive overview with graphs and community completion summaries.
    Accessible to Management group and superusers only.
    """
    template_name = 'Inventory/project_management_dashboard.html'
    
    def test_func(self):
        """Allow access to Management group members and superusers"""
        user = self.request.user
        return user.groups.filter(name='Management').exists() or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            # Get all BOQ items
            boq_items = BillOfQuantity.objects.all()
            
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
        return user.groups.filter(name='Management').exists() or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            boq_items = BillOfQuantity.objects.all()
            
            # Community-level aggregation with full data
            community_data = boq_items.values('community', 'region', 'district', 'phase').annotate(
                total_contract=Coalesce(Sum('contract_quantity'), 0.0),
                total_received=Coalesce(Sum('quantity_received'), 0.0),
                item_count=Count('id'),
                package_count=Count('package_number', distinct=True)
            ).order_by('community')
            
            # Process all communities
            community_list = []
            chart_labels = []
            chart_data = []
            completed_count = 0
            in_progress_count = 0
            not_started_count = 0
            
            for comm in community_data:
                if comm['community']:
                    completion = (comm['total_received'] / comm['total_contract'] * 100) if comm['total_contract'] > 0 else 0
                    status = 'Complete' if completion >= 100 else 'In Progress' if completion > 0 else 'Not Started'
                    
                    # Count by status
                    if status == 'Complete':
                        completed_count += 1
                    elif status == 'In Progress':
                        in_progress_count += 1
                    else:
                        not_started_count += 1
                    
                    community_list.append({
                        'name': comm['community'],
                        'region': comm['region'],
                        'district': comm['district'],
                        'phase': comm['phase'],
                        'total_contract': comm['total_contract'],
                        'total_received': comm['total_received'],
                        'balance': comm['total_contract'] - comm['total_received'],
                        'completion': round(completion, 2),
                        'item_count': comm['item_count'],
                        'package_count': comm['package_count'],
                        'status': status
                    })
                    chart_labels.append(comm['community'] or 'Unknown')
                    chart_data.append(round(completion, 2))
            
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
        return user.groups.filter(name='Management').exists() or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            boq_items = BillOfQuantity.objects.all()
            
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
        return user.groups.filter(name='Management').exists() or is_superuser(user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            boq_items = BillOfQuantity.objects.all()
            
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