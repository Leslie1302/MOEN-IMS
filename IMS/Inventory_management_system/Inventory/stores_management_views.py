# Inventory/stores_management_views.py
"""
Views for Stores Management workflow.
Handles the assignment of material orders to stores staff.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView
from django.db.models import Q, Count, Prefetch, Avg, F, ExpressionWrapper, fields
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction
from datetime import timedelta
import logging

from .models import MaterialOrder, StoreOrderAssignment, MaterialTransport
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


class StoresManagementMixin(UserPassesTestMixin):
    """Mixin to restrict access to Management group members who oversee stores"""
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        # Management group can assign orders to Store Officers
        return self.request.user.groups.filter(name='Management').exists()


class StoresStaffMixin(UserPassesTestMixin):
    """Mixin to restrict access to Store Officers who process orders house"""
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        # Store Officers process assigned orders
        return self.request.user.groups.filter(name='Store Officers').exists()


class PendingOrdersView(LoginRequiredMixin, StoresManagementMixin, ListView):
    """
    View for stores management to see all material orders waiting for approval/assignment.
    Shows orders in Draft or Pending status that haven't been assigned yet.
    """
    model = MaterialOrder
    template_name = 'Inventory/stores/pending_orders.html'
    context_object_name = 'orders'
    paginate_by = 50
    
    def get_queryset(self):
        """Get all orders that haven't been assigned to stores staff"""
        # Show all release request orders that don't have an assigned_to value yet
        # This allows retroactive assignment of existing orders
        queryset = MaterialOrder.objects.filter(
            request_type='Release',
            assigned_to__isnull=True  # Only show unassigned orders
        ).exclude(
            status='Completed'  # Don't show completed orders
        ).select_related(
            'user', 'unit', 'category', 'warehouse', 'created_by'
        ).prefetch_related(
            'store_assignments'
        ).annotate(
            assignment_count=Count('store_assignments')
        ).order_by('-date_requested')
        
        logger.info(f"Found {queryset.count()} unassigned orders awaiting assignment")
        
        # Filter by search query if provided
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(request_code__icontains=search) |
                Q(name__icontains=search) |
                Q(user__username__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get list of store officers for assignment dropdown
        stores_staff = User.objects.filter(
            groups__name='Store Officers',
            is_active=True
        ).order_by('username')
        
        context['stores_staff'] = stores_staff
        context['search_query'] = self.request.GET.get('search', '')
        
        # Statistics - count unassigned orders
        context['total_pending'] = MaterialOrder.objects.filter(
            request_type='Release',
            assigned_to__isnull=True
        ).exclude(
            status='Completed'
        ).count()
        
        return context


class AssignedOrdersView(LoginRequiredMixin, StoresManagementMixin, ListView):
    """
    View for stores management to see all orders that have been assigned.
    """
    model = StoreOrderAssignment
    template_name = 'Inventory/stores/assigned_orders.html'
    context_object_name = 'assignments'
    paginate_by = 50
    
    def get_queryset(self):
        """Get all store order assignments"""
        queryset = StoreOrderAssignment.objects.select_related(
            'material_order', 'material_order__user', 'material_order__unit',
            'assigned_to', 'assigned_by'
        ).order_by('-assigned_at')
        
        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by assigned staff
        staff_id = self.request.GET.get('staff', '')
        if staff_id:
            queryset = queryset.filter(assigned_to_id=staff_id)
        
        # Search
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(material_order__request_code__icontains=search) |
                Q(material_order__name__icontains=search) |
                Q(assigned_to__username__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get list of store officers
        stores_staff = User.objects.filter(
            groups__name='Store Officers',
            is_active=True
        ).order_by('username')
        
        context['stores_staff'] = stores_staff
        context['status_choices'] = StoreOrderAssignment.STATUS_CHOICES
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_staff'] = self.request.GET.get('staff', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        # Statistics
        stats = StoreOrderAssignment.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='Pending')),
            assigned=Count('id', filter=Q(status='Assigned')),
            in_progress=Count('id', filter=Q(status='In Progress')),
            completed=Count('id', filter=Q(status='Completed'))
        )
        context.update(stats)
        
        return context


class AssignOrderView(LoginRequiredMixin, StoresManagementMixin, View):
    """
    View to handle assignment of orders to stores staff.
    Supports both single and bulk assignment.
    """
    
    def post(self, request):
        """Handle order assignment"""
        try:
            # Get form data
            order_ids = request.POST.getlist('order_ids[]')
            staff_id = request.POST.get('staff_id')
            notes = request.POST.get('notes', '')
            
            if not order_ids:
                return JsonResponse({
                    'success': False,
                    'message': 'No orders selected for assignment'
                }, status=400)
            
            if not staff_id:
                return JsonResponse({
                    'success': False,
                    'message': 'No staff member selected'
                }, status=400)
            
            # Get the staff member
            try:
                staff_member = User.objects.get(id=staff_id)
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Selected staff member not found'
                }, status=404)
            
            # Ensure selected user is a Store Officer
            if not staff_member.groups.filter(name='Store Officer').exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Selected user is not a Store Officer and cannot be assigned store orders'
                }, status=400)
            
            # Process assignments in a transaction
            assigned_count = 0
            with transaction.atomic():
                for order_id in order_ids:
                    try:
                        order = MaterialOrder.objects.get(id=order_id)
                        
                        # Check if already assigned
                        existing_assignment = StoreOrderAssignment.objects.filter(
                            material_order=order,
                            status__in=['Pending', 'Assigned', 'In Progress']
                        ).first()
                        
                        if existing_assignment:
                            # Reassign
                            existing_assignment.reassign(
                                new_staff=staff_member,
                                reassigned_by=request.user,
                                notes=notes
                            )
                        else:
                            # Create new assignment
                            StoreOrderAssignment.objects.create(
                                material_order=order,
                                assigned_to=staff_member,
                                assigned_by=request.user,
                                status='Assigned',
                                assignment_notes=notes
                            )
                            
                            # Update MaterialOrder with assignment info
                            order.assigned_to = staff_member
                            order.assigned_by = request.user
                            order.assigned_at = timezone.now()
                            order.status = 'Approved'  # Mark as approved when assigned
                            order.last_updated_by = request.user
                            order.save()
                        
                        assigned_count += 1
                        
                    except MaterialOrder.DoesNotExist:
                        logger.warning(f"Order {order_id} not found during assignment")
                        continue
            
            # Success message
            if assigned_count > 0:
                messages.success(
                    request,
                    f'Successfully assigned {assigned_count} order(s) to {staff_member.username}'
                )
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully assigned {assigned_count} order(s)',
                    'redirect': request.META.get('HTTP_REFERER', '/material-orders/')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No orders were assigned'
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error assigning orders: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error assigning orders: {str(e)}'
            }, status=500)


class MyAssignedOrdersView(LoginRequiredMixin, StoresStaffMixin, ListView):
    """
    View for stores staff to see orders assigned to them.
    """
    model = StoreOrderAssignment
    template_name = 'Inventory/stores/my_assigned_orders.html'
    context_object_name = 'assignments'
    paginate_by = 50
    
    def get_queryset(self):
        """Get orders assigned to the current user"""
        queryset = StoreOrderAssignment.objects.filter(
            assigned_to=self.request.user
        ).select_related(
            'material_order', 'material_order__user', 'material_order__unit',
            'assigned_by'
        ).order_by('-assigned_at')
        
        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        
        # Search
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(material_order__request_code__icontains=search) |
                Q(material_order__name__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['status_choices'] = StoreOrderAssignment.STATUS_CHOICES
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        # Statistics for current user
        stats = StoreOrderAssignment.objects.filter(
            assigned_to=self.request.user
        ).aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='Pending')),
            assigned=Count('id', filter=Q(status='Assigned')),
            in_progress=Count('id', filter=Q(status='In Progress')),
            completed=Count('id', filter=Q(status='Completed'))
        )
        context.update(stats)
        
        return context


@login_required
@require_POST
def update_assignment_status(request, assignment_id):
    """
    Update the status of a store order assignment.
    Used by stores staff to mark progress on their assigned orders.
    """
    try:
        assignment = get_object_or_404(StoreOrderAssignment, id=assignment_id)
        
        # Check permissions
        if not (request.user == assignment.assigned_to or 
                request.user.groups.filter(name='Stores Management').exists() or
                request.user.is_superuser):
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to update this assignment'
            }, status=403)
        
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        if new_status == 'In Progress':
            assignment.mark_in_progress(user=request.user)
            messages.success(request, 'Assignment marked as in progress')
        elif new_status == 'Completed':
            assignment.mark_completed(notes=notes, user=request.user)
            messages.success(request, 'Assignment marked as completed')
        else:
            assignment.status = new_status
            assignment.save()
            messages.success(request, f'Assignment status updated to {new_status}')
        
        return JsonResponse({
            'success': True,
            'message': 'Status updated successfully',
            'new_status': assignment.status
        })
        
    except Exception as e:
        logger.error(f"Error updating assignment status: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error updating status: {str(e)}'
        }, status=500)


@login_required
def bulk_assign_orders(request):
    """
    Handle bulk assignment of orders to stores staff.
    """
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method'
        }, status=405)
    
    # Check if user is in Stores Management
    if not (request.user.groups.filter(name='Stores Management').exists() or 
            request.user.is_superuser):
        return JsonResponse({
            'success': False,
            'message': 'You do not have permission to assign orders'
        }, status=403)
    
    try:
        order_ids = request.POST.getlist('order_ids[]')
        staff_id = request.POST.get('staff_id')
        notes = request.POST.get('notes', '')
        
        if not order_ids:
            return JsonResponse({
                'success': False,
                'message': 'No orders selected'
            }, status=400)
        
        if not staff_id:
            return JsonResponse({
                'success': False,
                'message': 'No staff member selected'
            }, status=400)
        
        staff_member = get_object_or_404(User, id=staff_id)
        
        # Ensure selected user is a Store Officer
        if not staff_member.groups.filter(name='Store Officers').exists():
            return JsonResponse({
                'success': False,
                'message': 'Selected user is not a Store Officer and cannot be assigned store orders'
            }, status=400)
        
        assigned_count = 0
        with transaction.atomic():
            for order_id in order_ids:
                try:
                    order = MaterialOrder.objects.get(id=order_id)
                    
                    # Create assignment
                    StoreOrderAssignment.objects.create(
                        material_order=order,
                        assigned_to=staff_member,
                        assigned_by=request.user,
                        status='Assigned',
                        assignment_notes=notes
                    )
                    
                    # Update order status
                    order.status = 'Approved'
                    order.last_updated_by = request.user
                    order.save()
                    
                    assigned_count += 1
                    
                except MaterialOrder.DoesNotExist:
                    continue
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully assigned {assigned_count} order(s) to {staff_member.username}',
            'assigned_count': assigned_count
        })
        
    except Exception as e:
        logger.error(f"Error in bulk assignment: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


class StoreOfficerPerformanceDashboard(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Performance dashboard specifically for store officers.
    Shows individual performance metrics and team statistics.
    """
    model = User
    template_name = 'Inventory/stores/performance_dashboard.html'
    context_object_name = 'store_officers'
    
    def test_func(self):
        """Allow access to Store Officers and Management"""
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(name__in=['Store Officers', 'Management']).exists()
    
    def get_queryset(self):
        """Get all store officers"""
        return User.objects.filter(
            groups__name='Store Officers',
            is_active=True
        ).order_by('username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate performance grades for each store officer
        store_officer_grades = {}
        
        for store_officer in self.get_queryset():
            try:
                # Get all assignments for this store officer
                assignments = StoreOrderAssignment.objects.filter(
                    assigned_to=store_officer
                )
                
                total_tasks = assignments.count()
                completed_tasks = assignments.filter(status='Completed').count()
                
                # Calculate completion days for completed tasks
                completed_assignments = assignments.filter(
                    status='Completed',
                    completed_at__isnull=False
                ).annotate(
                    completion_days=ExpressionWrapper(
                        F('completed_at') - F('assigned_at'),
                        output_field=fields.DurationField()
                    )
                )
                
                # Calculate average completion time in days
                avg_completion_time = completed_assignments.aggregate(
                    avg_days=Avg('completion_days')
                )['avg_days']
                
                if avg_completion_time:
                    avg_completion_days = avg_completion_time.total_seconds() / (24 * 3600)
                else:
                    avg_completion_days = 0
                
                # Calculate performance score
                # 1. Completion Rate (40%)
                completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                completion_score = (completion_rate / 100) * 40
                
                # 2. Efficiency/Timeliness (30%)
                if avg_completion_days < 2:
                    efficiency_score = 30  # Excellent
                elif avg_completion_days < 5:
                    efficiency_score = 20  # Good
                elif avg_completion_days < 10:
                    efficiency_score = 10  # Average
                else:
                    efficiency_score = 0   # Needs improvement
                
                # 3. Volume/Productivity (30%)
                if completed_tasks >= 50:
                    volume_score = 30
                elif completed_tasks >= 30:
                    volume_score = 25
                elif completed_tasks >= 10:
                    volume_score = 15
                elif completed_tasks >= 1:
                    volume_score = 5
                else:
                    volume_score = 0
                
                # Total performance score
                performance_score = completion_score + efficiency_score + volume_score
                
                # Assign grade letter
                if performance_score >= 90:
                    grade_letter = 'A+'
                    grade_color = 'success'
                elif performance_score >= 85:
                    grade_letter = 'A'
                    grade_color = 'success'
                elif performance_score >= 80:
                    grade_letter = 'B+'
                    grade_color = 'info'
                elif performance_score >= 75:
                    grade_letter = 'B'
                    grade_color = 'info'
                elif performance_score >= 70:
                    grade_letter = 'C+'
                    grade_color = 'warning'
                elif performance_score >= 65:
                    grade_letter = 'C'
                    grade_color = 'warning'
                elif performance_score >= 60:
                    grade_letter = 'D'
                    grade_color = 'danger'
                elif total_tasks > 0:
                    grade_letter = 'F'
                    grade_color = 'danger'
                else:
                    grade_letter = 'N/A'
                    grade_color = 'secondary'
                    performance_score = 0
                
                store_officer_grades[store_officer.id] = {
                    'username': store_officer.username,
                    'first_name': store_officer.first_name,
                    'last_name': store_officer.last_name,
                    'grade': performance_score,
                    'grade_letter': grade_letter,
                    'grade_color': grade_color,
                    'total_tasks': total_tasks,
                    'completed_tasks': completed_tasks,
                    'avg_completion_days': avg_completion_days,
                    'completion_rate': completion_rate,
                    'completion_score': completion_score,
                    'efficiency_score': efficiency_score,
                    'volume_score': volume_score,
                }
                
                logger.info(f"✓ Store Officer {store_officer.username}: Grade={grade_letter}, Score={performance_score:.1f}, Tasks={completed_tasks}/{total_tasks}")
                
            except Exception as e:
                logger.error(f"✗ Error calculating grade for {store_officer.username}: {str(e)}", exc_info=True)
                # Add user with default values
                store_officer_grades[store_officer.id] = {
                    'username': store_officer.username,
                    'first_name': store_officer.first_name,
                    'last_name': store_officer.last_name,
                    'grade': 0,
                    'grade_letter': 'N/A',
                    'grade_color': 'secondary',
                    'total_tasks': 0,
                    'completed_tasks': 0,
                    'avg_completion_days': 0,
                    'completion_rate': 0,
                    'completion_score': 0,
                    'efficiency_score': 0,
                    'volume_score': 0,
                }
        
        # Sort by performance score and identify top performer
        sorted_grades = sorted(
            store_officer_grades.items(),
            key=lambda x: x[1]['grade'],
            reverse=True
        )
        
        # Mark top performer as "Store Officer of the Month"
        if sorted_grades and sorted_grades[0][1]['grade'] > 0:
            sorted_grades[0][1]['top_performer'] = True
        
        context['store_officer_grades'] = dict(sorted_grades)
        
        # Overall statistics
        all_assignments = StoreOrderAssignment.objects.all()
        context['total_assignments'] = all_assignments.count()
        context['pending_assignments'] = all_assignments.filter(status='Pending').count()
        context['in_progress_assignments'] = all_assignments.filter(status='In Progress').count()
        context['completed_assignments'] = all_assignments.filter(status='Completed').count()
        
        # Recent assignments
        context['recent_assignments'] = StoreOrderAssignment.objects.select_related(
            'material_order', 'assigned_to', 'assigned_by'
        ).order_by('-assigned_at')[:10]
        
        return context


class StoreOperationsHubView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Unified Store Operations Hub - Hybrid Dashboard.
    Combines Table, Kanban, and Timeline views with partial processing support.
    Role-based access: Store Officers see own orders, Management sees all, Schedule Officers see read-only.
    """
    model = MaterialOrder
    template_name = 'Inventory/stores/store_operations_hub.html'
    context_object_name = 'orders'
    paginate_by = 50
    
    def test_func(self):
        """Allow access to Store Officers, Management, Schedule Officers, Consultants, and Superusers"""
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        allowed_groups = ['Store Officers', 'Management', 'Schedule Officers', 'Consultants']
        return self.request.user.groups.filter(name__in=allowed_groups).exists()
    
    def get_user_role(self):
        """Determine the user's primary role for permissions"""
        user = self.request.user
        if user.is_superuser:
            return 'admin'
        if user.groups.filter(name='Store Officers').exists():
            return 'store_officer'
        if user.groups.filter(name='Management').exists():
            return 'management'
        if user.groups.filter(name='Schedule Officers').exists():
            return 'schedule_officer'
        if user.groups.filter(name='Consultants').exists():
            return 'consultant'
        return 'viewer'
    
    def get_queryset(self):
        """Get orders based on user role and filters"""
        user = self.request.user
        role = self.get_user_role()
        
        # Base queryset - all release type orders
        queryset = MaterialOrder.objects.filter(
            request_type='Release'
        ).select_related(
            'user', 'unit', 'category', 'warehouse', 'assigned_to', 'assigned_by'
        ).prefetch_related(
            'store_assignments', 'transports'
        ).order_by('-date_requested')
        
        # Role-based filtering
        if role == 'store_officer':
            # Store Officers see only orders assigned to them
            queryset = queryset.filter(assigned_to=user)
        elif role == 'consultant':
            # Consultants see orders for their region/district
            queryset = queryset.filter(
                Q(user=user) | Q(consultant=user.username)
            )
        # Management, Schedule Officers, Admin see all orders
        
        # Apply filters from request
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        
        date_filter = self.request.GET.get('date_range', '')
        if date_filter == 'today':
            queryset = queryset.filter(date_requested__date=timezone.now().date())
        elif date_filter == 'week':
            start_of_week = timezone.now().date() - timedelta(days=timezone.now().weekday())
            queryset = queryset.filter(date_requested__date__gte=start_of_week)
        elif date_filter == 'month':
            queryset = queryset.filter(
                date_requested__year=timezone.now().year,
                date_requested__month=timezone.now().month
            )
        
        # Search filter
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(request_code__icontains=search) |
                Q(name__icontains=search) |
                Q(user__username__icontains=search) |
                Q(assigned_to__username__icontains=search)
            )
        
        # Priority filter
        priority = self.request.GET.get('priority', '')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role = self.get_user_role()
        
        # User role info
        context['user_role'] = role
        context['can_process'] = role in ['store_officer', 'management', 'admin']
        context['can_assign'] = role in ['management', 'admin']
        
        # Current view mode (table, kanban, timeline)
        context['view_mode'] = self.request.GET.get('view', 'table')
        
        # Build base queryset for stats (same role-based filtering)
        if role == 'store_officer':
            base_qs = MaterialOrder.objects.filter(request_type='Release', assigned_to=user)
        elif role == 'consultant':
            base_qs = MaterialOrder.objects.filter(
                request_type='Release'
            ).filter(Q(user=user) | Q(consultant=user.username))
        else:
            base_qs = MaterialOrder.objects.filter(request_type='Release')
        
        # Statistics
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        
        stats = {
            'total_orders': base_qs.count(),
            'today_new': base_qs.filter(date_requested__date=today).count(),
            'pending_start': base_qs.filter(status__in=['Pending', 'Approved']).count(),
            'in_progress': base_qs.filter(status='In Progress').count(),
            'partially_fulfilled': base_qs.filter(status='Partially Fulfilled').count(),
            'completed': base_qs.filter(status='Completed').count(),
            'this_week_completed': base_qs.filter(
                status='Completed',
                date_requested__date__gte=week_start
            ).count(),
        }
        
        # Transport stats
        transport_stats = {
            'in_transit': MaterialTransport.objects.filter(
                status='In Transit',
                material_order__in=base_qs
            ).count(),
            'delivered': MaterialTransport.objects.filter(
                status='Delivered',
                material_order__in=base_qs
            ).count(),
        }
        stats.update(transport_stats)
        context['stats'] = stats
        
        # Kanban columns data
        if context['view_mode'] == 'kanban':
            context['kanban_columns'] = {
                'assigned': base_qs.filter(status__in=['Pending', 'Approved']).order_by('-date_requested')[:20],
                'in_progress': base_qs.filter(status='In Progress').order_by('-date_requested')[:20],
                'partial': base_qs.filter(status='Partially Fulfilled').order_by('-date_requested')[:20],
                'completed': base_qs.filter(status='Completed').order_by('-date_requested')[:20],
            }
        
        # Timeline data (recent activities)
        if context['view_mode'] == 'timeline':
            # Get recent orders with their activities
            context['timeline_items'] = base_qs.order_by('-date_requested')[:50]
        
        # Filter options
        context['status_choices'] = [
            ('Pending', 'Pending'),
            ('Approved', 'Approved'),
            ('In Progress', 'In Progress'),
            ('Partially Fulfilled', 'Partially Fulfilled'),
            ('Completed', 'Completed'),
        ]
        context['priority_choices'] = [
            ('Low', 'Low'),
            ('Medium', 'Medium'),
            ('High', 'High'),
            ('Urgent', 'Urgent'),
        ]
        context['date_range_choices'] = [
            ('today', 'Today'),
            ('week', 'This Week'),
            ('month', 'This Month'),
            ('', 'All Time'),
        ]
        
        # Current filter values
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_priority'] = self.request.GET.get('priority', '')
        context['selected_date_range'] = self.request.GET.get('date_range', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        # Store staff list for assignment (if user can assign)
        if context['can_assign']:
            context['stores_staff'] = User.objects.filter(
                groups__name='Store Officers',
                is_active=True
            ).order_by('username')
        
        return context


@login_required
@require_POST
def process_order_partial(request, order_id):
    """
    Process a partial quantity of an order.
    Supports incremental fulfillment with status transitions.
    """
    try:
        order = get_object_or_404(MaterialOrder, id=order_id)
        user = request.user
        
        # Check permissions
        can_process = (
            user.is_superuser or
            user == order.assigned_to or
            user.groups.filter(name='Management').exists()
        )
        
        if not can_process:
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to process this order'
            }, status=403)
        
        # Get quantity to process
        try:
            from decimal import Decimal
            quantity_to_process = Decimal(str(request.POST.get('quantity', 0)))
        except (ValueError, TypeError, Exception):
            return JsonResponse({
                'success': False,
                'message': 'Invalid quantity provided'
            }, status=400)
        
        if quantity_to_process <= 0:
            return JsonResponse({
                'success': False,
                'message': 'Quantity must be greater than zero'
            }, status=400)
        
        # Calculate remaining quantity
        current_processed = order.processed_quantity or Decimal('0')
        remaining = order.quantity - current_processed
        
        if quantity_to_process > remaining:
            return JsonResponse({
                'success': False,
                'message': f'Cannot process {quantity_to_process}. Only {remaining} remaining.'
            }, status=400)
        
        # Update order
        with transaction.atomic():
            new_processed = current_processed + quantity_to_process
            order.processed_quantity = new_processed
            
            # Determine new status based on fulfillment
            if new_processed >= order.quantity:
                order.status = 'Completed'
            elif new_processed > 0:
                order.status = 'Partially Fulfilled'
            else:
                order.status = 'In Progress'
            
            # Update remaining quantity
            order.remaining_quantity = order.quantity - new_processed
            order.last_updated_by = user
            order.save()
            
            # Update assignment if exists
            assignment = StoreOrderAssignment.objects.filter(
                material_order=order,
                assigned_to=user
            ).first()
            
            if assignment:
                if order.status == 'Completed':
                    assignment.status = 'Completed'
                    assignment.completed_at = timezone.now()
                elif order.status in ['Partially Fulfilled', 'In Progress']:
                    assignment.status = 'In Progress'
                    if not assignment.started_at:
                        assignment.started_at = timezone.now()
                assignment.save()
        
        logger.info(f"Order {order.request_code} processed: +{quantity_to_process}, total={new_processed}/{order.quantity}")
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully processed {quantity_to_process} {order.unit}',
            'order_id': order.id,
            'processed_quantity': new_processed,
            'remaining_quantity': order.remaining_quantity,
            'new_status': order.status,
            'fulfillment_percentage': round((new_processed / order.quantity) * 100, 1) if order.quantity > 0 else 0
        })
        
    except Exception as e:
        logger.error(f"Error processing order {order_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error processing order: {str(e)}'
        }, status=500)


@login_required
def store_hub_stats_api(request):
    """
    API endpoint to get real-time stats for the Store Operations Hub.
    Returns JSON data for dashboard widgets.
    """
    try:
        user = request.user
        
        # Determine role
        if user.is_superuser:
            role = 'admin'
        elif user.groups.filter(name='Store Officers').exists():
            role = 'store_officer'
        elif user.groups.filter(name='Management').exists():
            role = 'management'
        else:
            role = 'viewer'
        
        # Build queryset based on role
        if role == 'store_officer':
            base_qs = MaterialOrder.objects.filter(request_type='Release', assigned_to=user)
        else:
            base_qs = MaterialOrder.objects.filter(request_type='Release')
        
        today = timezone.now().date()
        
        stats = {
            'total': base_qs.count(),
            'today_new': base_qs.filter(date_requested__date=today).count(),
            'pending': base_qs.filter(status__in=['Pending', 'Approved']).count(),
            'in_progress': base_qs.filter(status='In Progress').count(),
            'partial': base_qs.filter(status='Partially Fulfilled').count(),
            'completed': base_qs.filter(status='Completed').count(),
        }
        
        return JsonResponse({'success': True, 'stats': stats})
        
    except Exception as e:
        logger.error(f"Error fetching hub stats: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

