"""
Weekly development report generator.
Composes professional email reports from parsed documentation and git data.
"""

from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

from .report_parser import DocumentationParser, GitAnalyzer
from .screenshot_scanner import ScreenshotScanner, ELI5Generator
from .pdf_generator import WeeklyReportPDFGenerator
from .activity_analyzer import ActivityAnalyzer
from ..models import WeeklyReport

logger = logging.getLogger(__name__)


class WeeklyReportGenerator:
    """
    Generates comprehensive weekly development reports.
    """
    
    def __init__(self, project_root=None, days=7):
        """
        Initialize report generator.
        
        Args:
            project_root: Path to project root (defaults to Django BASE_DIR)
            days: Number of days to include in report
        """
        self.project_root = project_root or settings.BASE_DIR
        self.days = days
        self.start_date = datetime.now().date() - timedelta(days=days)
        self.end_date = datetime.now().date()
        
        self.doc_parser = DocumentationParser(self.project_root)
        self.git_analyzer = GitAnalyzer(self.project_root)
        self.screenshot_scanner = ScreenshotScanner(self.project_root)
        self.eli5_generator = ELI5Generator()
        self.activity_analyzer = ActivityAnalyzer(self.start_date, self.end_date)
    
    def generate_report(self, user=None, custom_notes='', recipients=None, cc_recipients=None, dry_run=False):
        """
        Generate a complete weekly report.
        
        Args:
            user: User generating the report
            custom_notes: Additional custom notes to include
            recipients: List of recipient emails (uses settings if None)
            cc_recipients: List of CC emails
            dry_run: If True, don't send email, just return report
        
        Returns:
            WeeklyReport: Generated report object
        """
        logger.info(f"Generating weekly report for {self.start_date} to {self.end_date}")
        
        # Gather app activity data
        app_activities = self.activity_analyzer.analyze_all_activities()
        activity_summary = self.activity_analyzer.format_activity_summary(app_activities)
        logger.info(f"Analyzed app activities")
        
        # Gather git data
        commits = self.git_analyzer.get_commits(self.days)
        commit_stats = self.git_analyzer.get_commit_stats(self.days)
        categorized_commits = self.git_analyzer.categorize_commits(commits)
        
        migrations = self.doc_parser.scan_migration_files(self.days)
        readme_files = self.doc_parser.scan_readme_files()
        changelog_files = self.doc_parser.scan_changelog_files()
        todo_comments = self.doc_parser.scan_todo_fixme_comments(self.days)
        
        # Generate report sections
        executive_summary = self._generate_executive_summary(
            commit_stats, categorized_commits, migrations, activity_summary
        )
        
        new_features = self._generate_features_section(categorized_commits['features'])
        bug_fixes = self._generate_fixes_section(categorized_commits['fixes'])
        database_changes = self._generate_database_section(migrations)
        code_improvements = self._generate_improvements_section(
            categorized_commits['refactoring'],
            categorized_commits['documentation']
        )
        pending_tasks = self._generate_pending_tasks_section(todo_comments)
        next_priorities = self._generate_next_priorities_section(readme_files, changelog_files)
        
        # Create report object
        report = WeeklyReport(
            generated_by=user,
            start_date=self.start_date,
            end_date=self.end_date,
            subject=f"Weekly Development Report - {self.start_date.strftime('%b %d')} to {self.end_date.strftime('%b %d, %Y')}",
            executive_summary=executive_summary,
            new_features=new_features,
            bug_fixes=bug_fixes,
            database_changes=database_changes,
            code_improvements=code_improvements,
            pending_tasks=pending_tasks,
            next_priorities=next_priorities,
            custom_notes=custom_notes,
            recipients=','.join(recipients or self._get_default_recipients()),
            cc_recipients=','.join(cc_recipients or []),
            commits_analyzed=self.git_analyzer.commits_analyzed,
            files_scanned=self.doc_parser.scanned_files,
            migrations_found=len(migrations),
        )
        
        # Scan for screenshots
        screenshots = self.screenshot_scanner.find_recent_screenshots(self.days)
        screenshots_by_category = self.screenshot_scanner.categorize_screenshots(screenshots)
        logger.info(f"Found {len(screenshots)} screenshots")
        
        # Generate ELI5 explanations
        report_data = {
            'executive_summary': executive_summary,
            'new_features': new_features,
            'bug_fixes': bug_fixes,
            'database_changes': database_changes,
            'code_improvements': code_improvements,
            'pending_tasks': pending_tasks,
            'next_priorities': next_priorities,
        }
        eli5_sections = self.eli5_generator.generate_eli5_sections(report_data)
        
        # Generate email content
        html_content, plain_text_content = self._generate_email_content(report, commit_stats, screenshots_by_category)
        report.html_content = html_content
        report.plain_text_content = plain_text_content
        
        # Save report
        report.save()
        
        # Generate PDF attachment
        pdf_buffer = None
        try:
            from django.core.files.base import ContentFile
            pdf_generator = WeeklyReportPDFGenerator()
            pdf_buffer = pdf_generator.generate_pdf(report, screenshots[:5], eli5_sections)  # Limit to 5 screenshots
            
            # Save PDF to model
            pdf_filename = f"Weekly_Report_{report.report_id}.pdf"
            report.pdf_file.save(pdf_filename, ContentFile(pdf_buffer.getvalue()), save=True)
            
            logger.info(f"PDF generated and saved: {pdf_filename}")
        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}")
        
        # Generate ELI5 README
        try:
            eli5_readme = self.eli5_generator.create_eli5_readme(report, screenshots_by_category)
            # Save to file
            readme_path = self.project_root / 'WEEKLY_REPORT_ELI5.md'
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(eli5_readme)
            logger.info(f"ELI5 README saved to {readme_path}")
        except Exception as e:
            logger.error(f"Failed to generate ELI5 README: {e}")
        
        # Send email if not dry run
        if not dry_run:
            try:
                self._send_email(report, pdf_buffer)
                report.mark_as_sent()
                logger.info(f"Report {report.report_id} sent successfully")
            except Exception as e:
                error_msg = f"Failed to send report: {str(e)}"
                report.mark_as_failed(error_msg)
                logger.error(error_msg)
                raise
        else:
            logger.info(f"Dry run - report {report.report_id} not sent")
        
        return report
    
    def _generate_executive_summary(self, commit_stats, categorized_commits, migrations, activity_summary):
        """Generate executive summary section with app activity data."""
        summary_parts = []
        
        # App Activity Summary (Priority)
        if activity_summary:
            summary_parts.append("## Application Activity\n")
            summary_parts.append(activity_summary)
            summary_parts.append("\n")
        
        # Development Activity
        total_commits = commit_stats['total_commits']
        features_count = len(categorized_commits['features'])
        fixes_count = len(categorized_commits['fixes'])
        migrations_count = len(migrations)
        
        dev_summary = []
        
        if total_commits > 0:
            dev_summary.append(f"This week saw {total_commits} commit{'s' if total_commits != 1 else ''} to the codebase")
        
        if features_count > 0:
            dev_summary.append(f"{features_count} new feature{'s' if features_count != 1 else ''} implemented")
        
        if fixes_count > 0:
            dev_summary.append(f"{fixes_count} bug fix{'es' if fixes_count != 1 else ''} applied")
        
        if migrations_count > 0:
            dev_summary.append(f"{migrations_count} database migration{'s' if migrations_count != 1 else ''} created")
        
        if dev_summary:
            summary_parts.append("## Development Activity\n")
            summary = ". ".join(dev_summary) + "."
            
            # Add code statistics
            if commit_stats['insertions'] > 0 or commit_stats['deletions'] > 0:
                summary += f" Code changes included {commit_stats['insertions']:,} insertions and {commit_stats['deletions']:,} deletions across {commit_stats['files_changed']} files."
            
            summary_parts.append(summary)
        
        return "\n".join(summary_parts) if summary_parts else "No significant activity recorded this week."
    
    def _generate_features_section(self, feature_commits):
        """Generate new features section."""
        if not feature_commits:
            return "No new features implemented this week."
        
        features = []
        for commit in feature_commits:
            features.append(f"• {commit['message']} (by {commit['author']})")
        
        return "\n".join(features)
    
    def _generate_fixes_section(self, fix_commits):
        """Generate bug fixes section."""
        if not fix_commits:
            return "No bug fixes recorded this week."
        
        fixes = []
        for commit in fix_commits:
            fixes.append(f"• {commit['message']} (by {commit['author']})")
        
        return "\n".join(fixes)
    
    def _generate_database_section(self, migrations):
        """Generate database changes section."""
        if not migrations:
            return "No database migrations created this week."
        
        changes = []
        for migration in migrations:
            changes.append(f"• {migration['name']} - Modified {migration['modified'].strftime('%b %d, %Y')}")
        
        return "\n".join(changes)
    
    def _generate_improvements_section(self, refactor_commits, doc_commits):
        """Generate code improvements section."""
        improvements = []
        
        if refactor_commits:
            improvements.append("**Code Refactoring:**")
            for commit in refactor_commits:
                improvements.append(f"• {commit['message']}")
        
        if doc_commits:
            if improvements:
                improvements.append("")
            improvements.append("**Documentation Updates:**")
            for commit in doc_commits:
                improvements.append(f"• {commit['message']}")
        
        if not improvements:
            return "No code improvements or refactoring recorded this week."
        
        return "\n".join(improvements)
    
    def _generate_pending_tasks_section(self, todo_comments):
        """Generate pending tasks section."""
        if not todo_comments:
            return "No new pending tasks or known issues identified."
        
        tasks = []
        for comment in todo_comments[:10]:  # Limit to 10 most recent
            tasks.append(f"• [{comment['type']}] {comment['comment']} ({comment['file']})")
        
        if len(todo_comments) > 10:
            tasks.append(f"\n... and {len(todo_comments) - 10} more items")
        
        return "\n".join(tasks)
    
    def _generate_next_priorities_section(self, readme_files, changelog_files):
        """Generate next week's priorities section."""
        # Look for "Next" or "Upcoming" sections in documentation
        priorities = []
        
        for readme in readme_files:
            content = readme['content']
            # Look for sections like "## Next Steps", "## Upcoming", etc.
            import re
            next_section = re.search(r'##\s*(Next|Upcoming|TODO|Roadmap).*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
            if next_section:
                section_content = next_section.group(2).strip()
                if section_content:
                    priorities.append(section_content[:500])  # Limit length
                    break
        
        if not priorities:
            return "No specific priorities documented for next week. Continue with current development trajectory."
        
        return "\n".join(priorities)
    
    def _generate_email_content(self, report, commit_stats, screenshots_by_category=None):
        """
        Generate HTML and plain text email content.
        
        Args:
            report: WeeklyReport object
            commit_stats: Dictionary of commit statistics
            screenshots_by_category: Dictionary of categorized screenshots
        
        Returns:
            tuple: (html_content, plain_text_content)
        """
        context = {
            'report': report,
            'commit_stats': commit_stats,
            'generated_date': datetime.now(),
            'screenshots': screenshots_by_category or {},
        }
        
        # Generate HTML content
        try:
            html_content = render_to_string('Inventory/emails/weekly_report.html', context)
        except Exception as e:
            logger.warning(f"Could not render HTML template: {e}. Using fallback.")
            html_content = self._generate_fallback_html(report, commit_stats)
        
        # Generate plain text content
        try:
            plain_text_content = render_to_string('Inventory/emails/weekly_report.txt', context)
        except Exception as e:
            logger.warning(f"Could not render text template: {e}. Using fallback.")
            plain_text_content = self._generate_fallback_text(report, commit_stats)
        
        return html_content, plain_text_content
    
    def _generate_fallback_html(self, report, commit_stats):
        """Generate fallback HTML content if template is missing."""
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h1 style="color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px;">
                {report.subject}
            </h1>
            
            <div style="background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h2 style="color: #2980b9; margin-top: 0;">Executive Summary</h2>
                <p>{report.executive_summary}</p>
            </div>
            
            <h2 style="color: #27ae60;">New Features Implemented</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #27ae60;">{report.new_features}</pre>
            
            <h2 style="color: #e74c3c;">Bug Fixes and Issues Resolved</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #e74c3c;">{report.bug_fixes}</pre>
            
            <h2 style="color: #8e44ad;">Database Changes</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #8e44ad;">{report.database_changes}</pre>
            
            <h2 style="color: #f39c12;">Code Improvements and Refactoring</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #f39c12;">{report.code_improvements}</pre>
            
            <h2 style="color: #34495e;">Pending Tasks and Known Issues</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #34495e;">{report.pending_tasks}</pre>
            
            <h2 style="color: #16a085;">Next Week's Priorities</h2>
            <pre style="background: #f8f9fa; padding: 15px; border-left: 4px solid #16a085;">{report.next_priorities}</pre>
            
            {f'<div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;"><h3 style="margin-top: 0;">Custom Notes</h3><p>{report.custom_notes}</p></div>' if report.custom_notes else ''}
            
            <hr style="margin: 30px 0; border: none; border-top: 2px solid #ecf0f1;">
            
            <div style="font-size: 0.9em; color: #7f8c8d;">
                <p><strong>Report Statistics:</strong></p>
                <ul>
                    <li>Commits Analyzed: {report.commits_analyzed}</li>
                    <li>Files Scanned: {report.files_scanned}</li>
                    <li>Migrations Found: {report.migrations_found}</li>
                    <li>Report ID: {report.report_id}</li>
                    <li>Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</li>
                </ul>
            </div>
        </body>
        </html>
        """
        return html
    
    def _generate_fallback_text(self, report, commit_stats):
        """Generate fallback plain text content if template is missing."""
        text = f"""
{report.subject}
{'=' * len(report.subject)}

EXECUTIVE SUMMARY
-----------------
{report.executive_summary}

NEW FEATURES IMPLEMENTED
------------------------
{report.new_features}

BUG FIXES AND ISSUES RESOLVED
------------------------------
{report.bug_fixes}

DATABASE CHANGES
----------------
{report.database_changes}

CODE IMPROVEMENTS AND REFACTORING
----------------------------------
{report.code_improvements}

PENDING TASKS AND KNOWN ISSUES
-------------------------------
{report.pending_tasks}

NEXT WEEK'S PRIORITIES
----------------------
{report.next_priorities}

{'CUSTOM NOTES' if report.custom_notes else ''}
{'-------------' if report.custom_notes else ''}
{report.custom_notes if report.custom_notes else ''}

---
Report Statistics:
- Commits Analyzed: {report.commits_analyzed}
- Files Scanned: {report.files_scanned}
- Migrations Found: {report.migrations_found}
- Report ID: {report.report_id}
- Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
        """
        return text.strip()
    
    def _send_email(self, report, pdf_buffer=None):
        """
        Send the report via email with PDF attachment.
        
        Args:
            report: WeeklyReport object
            pdf_buffer: BytesIO buffer containing PDF file
        """
        subject = report.subject
        from_email = settings.DEFAULT_FROM_EMAIL
        to_emails = report.get_recipients_list()
        cc_emails = report.get_cc_recipients_list()
        
        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=report.plain_text_content,
            from_email=from_email,
            to=to_emails,
            cc=cc_emails
        )
        
        # Attach HTML version
        email.attach_alternative(report.html_content, "text/html")
        
        # Attach PDF if available
        if pdf_buffer:
            try:
                pdf_filename = f"Weekly_Report_{report.report_id}.pdf"
                email.attach(pdf_filename, pdf_buffer.read(), 'application/pdf')
                logger.info(f"PDF attached: {pdf_filename}")
            except Exception as e:
                logger.warning(f"Could not attach PDF: {e}")
        
        # Send
        email.send(fail_silently=False)
        
        logger.info(f"Email sent to {', '.join(to_emails)}")
    
    def _get_default_recipients(self):
        """Get default recipients from settings."""
        return getattr(settings, 'WEEKLY_REPORT_RECIPIENTS', [settings.ADMINS[0][1]] if settings.ADMINS else [])

