from datetime import datetime, timedelta
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.conf import settings

from Inventory.models import WeeklyReport, ReportSubmission
from Inventory.forms import ReportSubmissionForm

# Configure logger
logger = logging.getLogger(__name__)

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def generate_weekly_report(request):
    """
    View for generating weekly development reports.
    Accessible to staff and superuser roles.
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
            # Import WeeklyReportGenerator
            # Using absolute import to avoid relative import confusion in new package structure
            from Inventory.utils.report_generator import WeeklyReportGenerator
            
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
                    f'Report {report.report_id} generated and sent successfully!'
                )
            
            # Redirect to the report detail page
            return redirect('weeklyreport_changelist', report_id=report.pk)
        
        except Exception as e:
            messages.error(request, f'Failed to generate report: {str(e)}')
    
    # GET request - show form
    
    # Get default recipients from settings
    default_recipients = getattr(settings, 'WEEKLY_REPORT_RECIPIENTS', [])
    if not default_recipients and settings.ADMINS:
        default_recipients = [settings.ADMINS[0][1]]
    
    # Calculate default date range
    start_date = datetime.now().date() - timedelta(days=7)
    end_date = datetime.now().date()
    
    context = {
        'title': 'Generate Weekly Development Report',
        'default_recipients': ', '.join(default_recipients),
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'Inventory/generate_weekly_report.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def weeklyreport_changelist(request, report_id=None):
    """
    View for displaying weekly report details or list.
    Accessible to staff and superuser roles.
    """
    if report_id:
        # Show specific report detail
        report = get_object_or_404(WeeklyReport, pk=report_id)
        
        context = {
            'title': f'Weekly Report - {report.report_id}',
            'report': report,
            'object': report,
        }
        
        return render(request, 'Inventory/weeklyreport_detail.html', context)
    else:
        # Show list of all reports
        reports = WeeklyReport.objects.all().order_by('-generated_at')
        
        context = {
            'title': 'Weekly Reports',
            'reports': reports,
            'object_list': reports,
        }
        
        return render(request, 'Inventory/weekly_reports_list.html', context)


class ReportSubmissionListView(LoginRequiredMixin, ListView):
    model = ReportSubmission
    template_name = 'inventory/report_submission_list.html'
    context_object_name = 'reports'
    
    def get_queryset(self):
        # Show all reports to all users for transparency
        return ReportSubmission.objects.all()

class ReportSubmissionCreateView(LoginRequiredMixin, CreateView):
    model = ReportSubmission
    form_class = ReportSubmissionForm
    template_name = 'Inventory/report_submission_form.html'
    success_url = reverse_lazy('report-submission-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the full queryset for statistics (not paginated)
        full_queryset = self.get_queryset()
        
        # Add summary statistics using the full queryset
        if full_queryset.exists():
            context.update({
                'total_orders': full_queryset.count(),
                'pending_orders': full_queryset.filter(status='Pending').count(),
                'completed_orders': full_queryset.filter(status='Completed').count(),
                'partial_orders': full_queryset.filter(status='Partially Fulfilled').count(),
            })
        else:
            context.update({
                'total_orders': 0,
                'pending_orders': 0,
                'completed_orders': 0,
                'partial_orders': 0,
            })
        
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.group = self.request.user.groups.first()
        return super().form_valid(form)

class ReportSubmissionUpdateView(LoginRequiredMixin, UpdateView):
    model = ReportSubmission
    form_class = ReportSubmissionForm
    template_name = 'inventory/report_submission_form.html'
    success_url = reverse_lazy('report-submission-list')

    def get_queryset(self):
        # Only allow editing of draft reports
        if self.request.user.is_superuser:
            return ReportSubmission.objects.all()
        return ReportSubmission.objects.filter(
            user=self.request.user,
            status='Draft'
        )

class ReportSubmissionDetailView(LoginRequiredMixin, DetailView):
    model = ReportSubmission
    template_name = 'inventory/report_submission_detail.html'
    context_object_name = 'report'

    def get_queryset(self):
        # Show all reports to all users for transparency
        return ReportSubmission.objects.all()

def submit_report(request, pk):
    """View to handle report submission"""
    report = ReportSubmission.objects.get(pk=pk)
    if request.user == report.user and report.status == 'Draft':
        report.status = 'Submitted'
        report.save()
    return redirect('report-submission-list')

def approve_report(request, pk):
    """View to handle report approval"""
    if request.user.is_superuser:
        report = ReportSubmission.objects.get(pk=pk)
        if report.status == 'Submitted':
            report.status = 'Approved'
            report.save()
            # Create or update corresponding BOQ
            report.create_or_update_boq()
    return redirect('report-submission-list')

def reject_report(request, pk):
    """View to handle report rejection"""
    if request.user.is_superuser:
        report = ReportSubmission.objects.get(pk=pk)
        if report.status == 'Submitted':
            report.status = 'Rejected'
            report.save()
    return redirect('report-submission-list')
