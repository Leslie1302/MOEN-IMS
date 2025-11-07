"""
Activity analyzer for weekly reports.
Gathers data on inventory movements, receipts, transport, and other app activities.
"""

import logging
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class ActivityAnalyzer:
    """
    Analyzes app activity for weekly reports.
    """
    
    def __init__(self, start_date, end_date):
        """
        Initialize activity analyzer.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
        """
        self.start_date = start_date
        self.end_date = end_date
    
    def analyze_all_activities(self):
        """
        Analyze all app activities for the reporting period.
        
        Returns:
            dict: Dictionary containing all activity metrics
        """
        return {
            'inventory': self.analyze_inventory_movements(),
            'material_orders': self.analyze_material_orders(),
            'boq': self.analyze_boq_activities(),
            'users': self.analyze_user_activities(),
            'notifications': self.analyze_notifications(),
        }
    
    def analyze_inventory_movements(self):
        """Analyze inventory item activities."""
        from ..models import InventoryItem
        
        try:
            # Get items created/updated in period
            items_created = InventoryItem.objects.filter(
                created_at__gte=self.start_date,
                created_at__lte=self.end_date
            ).count()
            
            items_updated = InventoryItem.objects.filter(
                updated_at__gte=self.start_date,
                updated_at__lte=self.end_date
            ).exclude(
                created_at__gte=self.start_date
            ).count()
            
            # Get low stock items
            low_stock_items = InventoryItem.objects.filter(
                quantity__lte=3
            ).count()
            
            # Get total quantity changes
            total_items = InventoryItem.objects.count()
            total_quantity = InventoryItem.objects.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            return {
                'items_created': items_created,
                'items_updated': items_updated,
                'low_stock_items': low_stock_items,
                'total_items': total_items,
                'total_quantity': total_quantity,
            }
        except Exception as e:
            logger.error(f"Error analyzing inventory: {e}")
            return {}
    
    def analyze_material_orders(self):
        """Analyze material order activities."""
        from ..models import MaterialOrder
        
        try:
            # Orders created in period
            orders_created = MaterialOrder.objects.filter(
                date_requested__gte=self.start_date,
                date_requested__lte=self.end_date
            ).count()
            
            # Orders processed in period
            orders_processed = MaterialOrder.objects.filter(
                processed_at__gte=self.start_date,
                processed_at__lte=self.end_date
            ).count()
            
            # Orders by status
            status_breakdown = MaterialOrder.objects.filter(
                date_requested__gte=self.start_date,
                date_requested__lte=self.end_date
            ).values('status').annotate(count=Count('id'))
            
            # Orders by type
            type_breakdown = MaterialOrder.objects.filter(
                date_requested__gte=self.start_date,
                date_requested__lte=self.end_date
            ).values('request_type').annotate(count=Count('id'))
            
            # Pending orders
            pending_orders = MaterialOrder.objects.filter(
                status='Pending'
            ).count()
            
            return {
                'orders_created': orders_created,
                'orders_processed': orders_processed,
                'pending_orders': pending_orders,
                'status_breakdown': list(status_breakdown),
                'type_breakdown': list(type_breakdown),
            }
        except Exception as e:
            logger.error(f"Error analyzing material orders: {e}")
            return {}
    
    def analyze_boq_activities(self):
        """Analyze Bill of Quantity activities."""
        from ..models import BillOfQuantity, BoQOverissuanceJustification
        
        try:
            # BOQ items created
            boq_created = BillOfQuantity.objects.filter(
                date_created__gte=self.start_date,
                date_created__lte=self.end_date
            ).count()
            
            # BOQ items by region
            region_breakdown = BillOfQuantity.objects.filter(
                date_created__gte=self.start_date,
                date_created__lte=self.end_date
            ).values('region').annotate(count=Count('id'))
            
            # Overissuance justifications
            justifications_submitted = BoQOverissuanceJustification.objects.filter(
                submitted_at__gte=self.start_date,
                submitted_at__lte=self.end_date
            ).count()
            
            justifications_reviewed = BoQOverissuanceJustification.objects.filter(
                reviewed_at__gte=self.start_date,
                reviewed_at__lte=self.end_date
            ).count()
            
            # Pending justifications
            pending_justifications = BoQOverissuanceJustification.objects.filter(
                status='Pending'
            ).count()
            
            return {
                'boq_created': boq_created,
                'region_breakdown': list(region_breakdown),
                'justifications_submitted': justifications_submitted,
                'justifications_reviewed': justifications_reviewed,
                'pending_justifications': pending_justifications,
            }
        except Exception as e:
            logger.error(f"Error analyzing BOQ: {e}")
            return {}
    
    def analyze_user_activities(self):
        """Analyze user activities."""
        from django.contrib.auth.models import User
        from ..models import Profile
        
        try:
            # New users
            users_created = User.objects.filter(
                date_joined__gte=self.start_date,
                date_joined__lte=self.end_date
            ).count()
            
            # Active users (logged in during period)
            active_users = User.objects.filter(
                last_login__gte=self.start_date,
                last_login__lte=self.end_date
            ).count()
            
            # Total users
            total_users = User.objects.count()
            
            # Users by group
            from django.contrib.auth.models import Group
            group_breakdown = []
            for group in Group.objects.all():
                count = group.user_set.count()
                if count > 0:
                    group_breakdown.append({'group': group.name, 'count': count})
            
            # Signatures created
            signatures_created = Profile.objects.filter(
                signature_stamp__isnull=False
            ).exclude(
                signature_stamp=''
            ).count()
            
            return {
                'users_created': users_created,
                'active_users': active_users,
                'total_users': total_users,
                'group_breakdown': group_breakdown,
                'signatures_created': signatures_created,
            }
        except Exception as e:
            logger.error(f"Error analyzing users: {e}")
            return {}
    
    def analyze_notifications(self):
        """Analyze notification activities."""
        from ..models import Notification
        
        try:
            # Notifications sent
            notifications_sent = Notification.objects.filter(
                created_at__gte=self.start_date,
                created_at__lte=self.end_date
            ).count()
            
            # Notifications read
            notifications_read = Notification.objects.filter(
                read_at__gte=self.start_date,
                read_at__lte=self.end_date
            ).count()
            
            # Unread notifications
            unread_notifications = Notification.objects.filter(
                is_read=False
            ).count()
            
            # Notifications by type
            type_breakdown = Notification.objects.filter(
                created_at__gte=self.start_date,
                created_at__lte=self.end_date
            ).values('notification_type').annotate(count=Count('id'))
            
            return {
                'notifications_sent': notifications_sent,
                'notifications_read': notifications_read,
                'unread_notifications': unread_notifications,
                'type_breakdown': list(type_breakdown),
            }
        except Exception as e:
            logger.error(f"Error analyzing notifications: {e}")
            return {}
    
    def format_activity_summary(self, activities):
        """
        Format activity data into human-readable summary.
        
        Args:
            activities: Dictionary of activity data
        
        Returns:
            str: Formatted summary text
        """
        summary_parts = []
        
        # Inventory summary
        inv = activities.get('inventory', {})
        if inv:
            summary_parts.append(f"**Inventory Management:**")
            summary_parts.append(f"• {inv.get('items_created', 0)} new items added to inventory")
            summary_parts.append(f"• {inv.get('items_updated', 0)} items updated")
            summary_parts.append(f"• {inv.get('low_stock_items', 0)} items currently low in stock")
            summary_parts.append(f"• Total inventory: {inv.get('total_items', 0)} items ({inv.get('total_quantity', 0)} units)")
            summary_parts.append("")
        
        # Material orders summary
        orders = activities.get('material_orders', {})
        if orders:
            summary_parts.append(f"**Material Orders:**")
            summary_parts.append(f"• {orders.get('orders_created', 0)} new orders submitted")
            summary_parts.append(f"• {orders.get('orders_processed', 0)} orders processed")
            summary_parts.append(f"• {orders.get('pending_orders', 0)} orders pending")
            
            if orders.get('status_breakdown'):
                summary_parts.append(f"• Status breakdown:")
                for status in orders['status_breakdown']:
                    summary_parts.append(f"  - {status['status']}: {status['count']}")
            summary_parts.append("")
        
        # BOQ summary
        boq = activities.get('boq', {})
        if boq:
            summary_parts.append(f"**Bill of Quantity (BOQ):**")
            summary_parts.append(f"• {boq.get('boq_created', 0)} BOQ items created")
            summary_parts.append(f"• {boq.get('justifications_submitted', 0)} overissuance justifications submitted")
            summary_parts.append(f"• {boq.get('justifications_reviewed', 0)} justifications reviewed")
            summary_parts.append(f"• {boq.get('pending_justifications', 0)} justifications pending review")
            summary_parts.append("")
        
        # User activity summary
        users = activities.get('users', {})
        if users:
            summary_parts.append(f"**User Activity:**")
            summary_parts.append(f"• {users.get('users_created', 0)} new users registered")
            summary_parts.append(f"• {users.get('active_users', 0)} users logged in this week")
            summary_parts.append(f"• Total users: {users.get('total_users', 0)}")
            
            if users.get('group_breakdown'):
                summary_parts.append(f"• Users by role:")
                for group in users['group_breakdown']:
                    summary_parts.append(f"  - {group['group']}: {group['count']}")
            summary_parts.append("")
        
        # Notifications summary
        notifs = activities.get('notifications', {})
        if notifs:
            summary_parts.append(f"**Notifications:**")
            summary_parts.append(f"• {notifs.get('notifications_sent', 0)} notifications sent")
            summary_parts.append(f"• {notifs.get('notifications_read', 0)} notifications read")
            summary_parts.append(f"• {notifs.get('unread_notifications', 0)} unread notifications")
            summary_parts.append("")
        
        return "\n".join(summary_parts) if summary_parts else "No significant app activity recorded this week."
