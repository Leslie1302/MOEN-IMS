"""
Admin interface for weekly development reports.
Provides custom admin views and actions for generating and managing reports.
"""

from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from datetime import datetime, timedelta

from .models import WeeklyReport
from .utils.report_generator import WeeklyReportGenerator


@admin.register(WeeklyReport)
class WeeklyReportAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing and managing weekly reports.
    """
    change_list_template = 'admin/Inventory/weeklyreport_changelist.html'
    list_display = ('report_id', 'date_range', 'status_badge', 'generated_by', 'generated_at', 'recipients_count', 'download_pdf', 'view_report')
    list_filter = ('status', 'generated_at', 'start_date')
    search_fields = ('report_id', 'subject', 'recipients', 'executive_summary')
    readonly_fields = (
        'report_id', 'generated_by', 'generated_at', 'sent_at',
        'commits_analyzed', 'files_scanned', 'migrations_found',
        'html_preview', 'plain_text_preview'
    )
    actions = ['resend_failed_reports']
    
    fieldsets = (
        ('Report Information', {
            'fields': ('report_id', 'generated_by', 'generated_at', 'status', 'sent_at')
        }),
        ('Date Range', {
            'fields': ('start_date', 'end_date')
        }),
        ('Email Details', {
            'fields': ('subject', 'recipients', 'cc_recipients')
        }),
        ('Report Content', {
            'fields': ('executive_summary', 'new_features', 'bug_fixes', 'database_changes', 
                      'code_improvements', 'pending_tasks', 'next_priorities', 'custom_notes'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('commits_analyzed', 'files_scanned', 'migrations_found')
        }),
        ('Email Content Preview', {
            'fields': ('html_preview', 'plain_text_preview'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )
    
    def get_urls(self):
        """Add custom admin URLs."""
        urls = super().get_urls()
        custom_urls = [
            path('generate/', self.admin_site.admin_view(self.generate_report_view), name='inventory_weeklyreport_generate'),
        ]
        return custom_urls + urls
    
    def date_range(self, obj):
        """Display date range."""
        return f"{obj.start_date.strftime('%b %d')} - {obj.end_date.strftime('%b %d, %Y')}"
    date_range.short_description = 'Period'
    
    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            'draft': '#6c757d',
            'sent': '#28a745',
            'failed': '#dc3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def recipients_count(self, obj):
        """Display number of recipients."""
        count = len(obj.get_recipients_list())
        cc_count = len(obj.get_cc_recipients_list())
        if cc_count > 0:
            return f"{count} (+ {cc_count} CC)"
        return str(count)
    recipients_count.short_description = 'Recipients'
    
    def download_pdf(self, obj):
        """Link to download PDF."""
        if obj.pdf_file:
            return format_html(
                '<a href="{}" class="button" download>📄 Download PDF</a>',
                obj.pdf_file.url
            )
        return "No PDF"
    download_pdf.short_description = 'PDF'
    
    def view_report(self, obj):
        """Link to view full report."""
        return format_html(
            '<a href="{}" class="button">View Report</a>',
            f'/admin/Inventory/weeklyreport/{obj.pk}/change/'
        )
    view_report.short_description = 'Actions'
    
    def html_preview(self, obj):
        """Preview HTML content."""
        if obj.html_content:
            return mark_safe(f'<div style="max-height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px;">{obj.html_content}</div>')
        return "No HTML content"
    html_preview.short_description = 'HTML Email Preview'
    
    def plain_text_preview(self, obj):
        """Preview plain text content."""
        if obj.plain_text_content:
            return mark_safe(f'<pre style="max-height: 400px; overflow-y: auto; background: #f5f5f5; padding: 10px;">{obj.plain_text_content}</pre>')
        return "No plain text content"
    plain_text_preview.short_description = 'Plain Text Email Preview'
    
    def generate_report_view(self, request):
        """
        Custom admin view for generating weekly reports.
        """
        if request.method == 'POST':
            # Get form data
            days = int(request.POST.get('days', 7))
            custom_notes = request.POST.get('custom_notes', '')
            recipients = request.POST.get('recipients', '').strip()
            cc_recipients = request.POST.get('cc_recipients', '').strip()
            dry_run = request.POST.get('dry_run') == 'on'
            
            # Parse recipients
            recipients_list = [email.strip() for email in recipients.split(',') if email.strip()] if recipients else None
            cc_list = [email.strip() for email in cc_recipients.split(',') if email.strip()] if cc_recipients else None
            
            try:
                # Generate report
                generator = WeeklyReportGenerator(days=days)
                report = generator.generate_report(
                    user=request.user,
                    custom_notes=custom_notes,
                    recipients=recipients_list,
                    cc_recipients=cc_list,
                    dry_run=dry_run
                )
                
                if dry_run:
                    messages.success(
                        request,
                        f'Report {report.report_id} generated successfully (DRY RUN - not sent). '
                        f'View it in the reports list.'
                    )
                else:
                    messages.success(
                        request,
                        f'Report {report.report_id} generated and sent successfully to {report.recipients}!'
                    )
                
                # Redirect to the report detail page
                return redirect(f'/admin/Inventory/weeklyreport/{report.pk}/change/')
            
            except Exception as e:
                messages.error(request, f'Failed to generate report: {str(e)}')
        
        # GET request - show form
        from django.conf import settings
        
        # Get default recipients from settings
        default_recipients = getattr(settings, 'WEEKLY_REPORT_RECIPIENTS', [])
        if not default_recipients and settings.ADMINS:
            default_recipients = [settings.ADMINS[0][1]]
        
        # Calculate default date range
        start_date = datetime.now().date() - timedelta(days=7)
        end_date = datetime.now().date()
        
        context = {
            'title': 'Generate Weekly Development Report',
            'site_title': 'MOEN IMS Admin',
            'site_header': 'MOEN IMS Administration',
            'has_permission': True,
            'opts': WeeklyReport._meta,
            'default_recipients': ', '.join(default_recipients),
            'start_date': start_date,
            'end_date': end_date,
        }
        
        return render(request, 'admin/Inventory/generate_weekly_report.html', context)
    
    def changelist_view(self, request, extra_context=None):
        """Add custom button to changelist."""
        extra_context = extra_context or {}
        extra_context['generate_report_url'] = '/admin/Inventory/weeklyreport/generate/'
        return super().changelist_view(request, extra_context=extra_context)
    
    def resend_failed_reports(self, request, queryset):
        """Resend failed reports."""
        failed_reports = queryset.filter(status='failed')
        
        if not failed_reports.exists():
            messages.warning(request, 'No failed reports selected.')
            return
        
        success_count = 0
        fail_count = 0
        
        for report in failed_reports:
            try:
                # Re-send the report
                from django.core.mail import EmailMultiAlternatives
                from django.conf import settings
                
                email = EmailMultiAlternatives(
                    subject=report.subject,
                    body=report.plain_text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=report.get_recipients_list(),
                    cc=report.get_cc_recipients_list()
                )
                email.attach_alternative(report.html_content, "text/html")
                email.send(fail_silently=False)
                
                report.mark_as_sent()
                success_count += 1
            
            except Exception as e:
                report.mark_as_failed(str(e))
                fail_count += 1
        
        if success_count > 0:
            messages.success(request, f'Successfully resent {success_count} report(s).')
        if fail_count > 0:
            messages.error(request, f'Failed to resend {fail_count} report(s).')
    
    resend_failed_reports.short_description = 'Resend failed reports'
