import secrets
import string
import logging
import pandas as pd
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import View
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from Inventory.models import Profile, MaterialOrder
from Inventory.forms import (
    UserUpdateForm, ProfileUpdateForm, PasswordChangeForm, 
    BulkUserUploadForm
)

# Configure logger
logger = logging.getLogger(__name__)

class ProfileView(LoginRequiredMixin, View):
    template_name = 'Inventory/profile.html'
    permission_required = 'Inventory.view_profile'

    def get(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        context = {
            'user_form': UserUpdateForm(instance=request.user),
            'profile_form': ProfileUpdateForm(instance=profile),
            'password_form': PasswordChangeForm(),
            'profile': profile
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        password_form = PasswordChangeForm(request.POST)
        
        if 'update_info' in request.POST:
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated!')
                return redirect('profile')
        elif 'change_password' in request.POST:
            if password_form.is_valid():
                user = request.user
                if user.check_password(password_form.cleaned_data['old_password']):
                    user.set_password(password_form.cleaned_data['new_password'])
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Your password has been updated!')
                    return redirect('profile')
                else:
                    messages.error(request, 'Old password is incorrect.')
        
        context = {
            'user_form': user_form,
            'profile_form': profile_form,
            'password_form': password_form,
            'profile': profile
        }
        return render(request, self.template_name, context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def bulk_user_upload(request):
    """
    View for bulk creating user accounts via Excel file.
    Only accessible to superusers.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    
    if request.method == 'POST':
        form = BulkUserUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            df = form.cleaned_data['df']
            user_group = form.cleaned_data.get('user_group')
            send_welcome_email = form.cleaned_data.get('send_welcome_email', False)
            
            # Track results
            created_users = []
            skipped_users = []
            failed_users = []
            
            try:
                with transaction.atomic():
                    for index, row in df.iterrows():
                        username = str(row['username']).strip()
                        name = str(row.get('name', '')).strip()
                        email = str(row['email']).strip()
                        
                        # Check if user already exists
                        if User.objects.filter(username=username).exists():
                            skipped_users.append({
                                'username': username,
                                'reason': 'Username already exists'
                            })
                            continue
                        
                        if User.objects.filter(email=email).exists():
                            skipped_users.append({
                                'username': username,
                                'reason': 'Email already exists'
                            })
                            continue
                        
                        # Generate random password (12 characters)
                        alphabet = string.ascii_letters + string.digits
                        password = ''.join(secrets.choice(alphabet) for i in range(12))
                        
                        try:
                            # Create user
                            user = User.objects.create_user(
                                username=username,
                                email=email,
                                password=password
                            )
                            
                            # Set first and last name from 'name' field
                            if name:
                                name_parts = name.split(' ', 1)
                                user.first_name = name_parts[0]
                                if len(name_parts) > 1:
                                    user.last_name = name_parts[1]
                                user.save()
                            
                            # Add to group if specified
                            if user_group:
                                user.groups.add(user_group)
                            
                            # Create profile if it doesn't exist
                            Profile.objects.get_or_create(user=user)
                            
                            created_users.append({
                                'username': username,
                                'email': email,
                                'password': password,
                                'name': name
                            })
                            
                            logger.info(f"Created user: {username}")
                            
                        except Exception as e:
                            failed_users.append({
                                'username': username,
                                'reason': str(e)
                            })
                            logger.error(f"Failed to create user {username}: {str(e)}")
                
                # Send welcome emails if requested
                if send_welcome_email and created_users:
                    for user_info in created_users:
                        try:
                            subject = 'Welcome to MOEN IMS - Your Account Credentials'
                            message = f"""
Hello {user_info['name'] or user_info['username']},

Your account has been created in the MOEN Inventory Management System.

Login Credentials:
Username: {user_info['username']}
Password: {user_info['password']}

Please login and change your password immediately.

Login URL: {request.build_absolute_uri('/signin/')}

Best regards,
MOEN IMS Team
                            """
                            
                            send_mail(
                                subject,
                                message,
                                settings.DEFAULT_FROM_EMAIL,
                                [user_info['email']],
                                fail_silently=True
                            )
                        except Exception as e:
                            logger.error(f"Failed to send email to {user_info['email']}: {str(e)}")
                
                # Display results
                if created_users:
                    messages.success(
                        request,
                        f"Successfully created {len(created_users)} user account(s)!"
                    )
                
                if skipped_users:
                    messages.warning(
                        request,
                        f"Skipped {len(skipped_users)} user(s) due to existing usernames/emails."
                    )
                
                if failed_users:
                    messages.error(
                        request,
                        f"Failed to create {len(failed_users)} user(s). Check the details below."
                    )
                
                # Store results in context for display
                context = {
                    'form': BulkUserUploadForm(),  # New empty form
                    'created_users': created_users,
                    'skipped_users': skipped_users,
                    'failed_users': failed_users,
                    'show_results': True
                }
                
                return render(request, 'Inventory/bulk_user_upload.html', context)
                
            except Exception as e:
                messages.error(request, f"Error processing upload: {str(e)}")
                logger.error(f"Bulk user upload error: {str(e)}", exc_info=True)
    else:
        form = BulkUserUploadForm()
    
    context = {
        'form': form,
        'title': 'Bulk User Upload',
        'show_results': False
    }
    
    return render(request, 'Inventory/bulk_user_upload.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def download_user_template(request):
    """Download sample Excel template for bulk user upload"""
    # Sample data for the template
    sample_data = {
        'username': ['jdoe', 'asmith', 'bwilson'],
        'name': ['John Doe', 'Alice Smith', 'Bob Wilson'],
        'email': ['john.doe@example.com', 'alice.smith@example.com', 'bob.wilson@example.com']
    }
    
    # Create DataFrame
    df = pd.DataFrame(sample_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Users')
    
    output.seek(0)
    
    # Create HTTP response
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="user_upload_template.xlsx"'
    
    return response


class StaffProfileView(LoginRequiredMixin, View):
    """
    Comprehensive staff profile view showing detailed metrics and activities for a specific user.
    Accessible to superusers and management users.
    """
    
    def get(self, request, username):
        # Ensure only superusers and management can access staff profiles
        if not (request.user.is_superuser or request.user.groups.filter(name='Management').exists()):
            return redirect('dashboard')
        
        try:
            # Get the target user
            target_user = get_object_or_404(User, username=username)
            
            # Get or create the user's profile
            try:
                target_profile = target_user.profile
            except Profile.DoesNotExist:
                target_profile = Profile.objects.create(user=target_user)
            
            # Get date range for filtering (default to last 30 days)
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
            
            # Material Orders Statistics
            user_orders = MaterialOrder.objects.filter(user=target_user)
            recent_orders = user_orders.filter(date_requested__date__gte=start_date)
            
            order_stats = {
                'total_orders': user_orders.count(),
                'recent_orders': recent_orders.count(),
                'pending_orders': user_orders.filter(status='Pending').count(),
                'completed_orders': user_orders.filter(status='Completed').count(),
                'draft_orders': user_orders.filter(status='Draft').count(),
                'partially_fulfilled': user_orders.filter(status='Partially Fulfilled').count(),
            }
            
            # Request Type Breakdown
            release_orders = user_orders.filter(request_type='Release').count()
            receipt_orders = user_orders.filter(request_type='Receipt').count()
            
            # Recent Activity (Material Orders)
            recent_material_orders = recent_orders.order_by('-date_requested')[:10]
            
            # Audit Log Activity
            try:
                from audit_log.models import AuditLog
                user_audit_logs = AuditLog.objects.filter(user=target_user).order_by('-timestamp')[:20]
                audit_stats = {
                    'total_actions': AuditLog.objects.filter(user=target_user).count(),
                    'recent_actions': AuditLog.objects.filter(
                        user=target_user, 
                        timestamp__date__gte=start_date
                    ).count(),
                }
            except ImportError:
                user_audit_logs = []
                audit_stats = {'total_actions': 0, 'recent_actions': 0}
            
            # Performance Calculation (based on order completion rate)
            if order_stats['total_orders'] > 0:
                completion_rate = (order_stats['completed_orders'] / order_stats['total_orders']) * 100
                if completion_rate >= 90:
                    performance_grade = 'A'
                    performance_color = 'success'
                elif completion_rate >= 80:
                    performance_grade = 'B'
                    performance_color = 'info'
                elif completion_rate >= 70:
                    performance_grade = 'C'
                    performance_color = 'warning'
                else:
                    performance_grade = 'D'
                    performance_color = 'danger'
            else:
                performance_grade = 'N/A'
                performance_color = 'secondary'
                
            context = {
                'target_user': target_user,
                'target_profile': target_profile,
                'order_stats': order_stats,
                'audit_stats': audit_stats,
                'recent_material_orders': recent_material_orders,
                'user_audit_logs': user_audit_logs,
                'performance_grade': performance_grade,
                'performance_color': performance_color,
                'release_orders': release_orders,
                'receipt_orders': receipt_orders,
            }
            
            return render(request, 'inventory/staff_profile.html', context)
            
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('dashboard')
        except Exception as e:
            logger.error(f"Error viewing staff profile: {str(e)}", exc_info=True)
            messages.error(request, 'An error occurred while loading the profile.')
            return redirect('dashboard')
