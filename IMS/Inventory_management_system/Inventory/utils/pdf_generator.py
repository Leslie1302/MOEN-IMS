"""
PDF generator for weekly development reports.
Creates professional PDF documents with screenshots and formatted content.
"""

import os
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image,
    Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


class WeeklyReportPDFGenerator:
    """
    Generates PDF version of weekly development reports.
    """
    
    def __init__(self):
        """Initialize PDF generator with styles."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Create custom paragraph styles."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#3498db'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold',
            borderWidth=2,
            borderColor=colors.HexColor('#3498db'),
            borderPadding=5,
            backColor=colors.HexColor('#ecf0f1')
        ))
        
        # Subsection header style
        self.styles.add(ParagraphStyle(
            name='SubsectionHeader',
            parent=self.styles['Heading3'],
            fontSize=13,
            textColor=colors.HexColor('#2980b9'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))
        
        # Body text style
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['BodyText'],
            fontSize=11,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=10
        ))
        
        # Code/preformatted style
        self.styles.add(ParagraphStyle(
            name='CodeBlock',
            parent=self.styles['Code'],
            fontSize=9,
            leading=12,
            backColor=colors.HexColor('#f8f9fa'),
            borderWidth=1,
            borderColor=colors.HexColor('#dee2e6'),
            borderPadding=8,
            leftIndent=10,
            rightIndent=10,
            fontName='Courier'
        ))
        
        # Bullet point style
        self.styles.add(ParagraphStyle(
            name='BulletPoint',
            parent=self.styles['BodyText'],
            fontSize=10,
            leading=14,
            leftIndent=20,
            bulletIndent=10,
            spaceAfter=6
        ))
        
        # ELI5 style (friendly, simple language)
        self.styles.add(ParagraphStyle(
            name='ELI5',
            parent=self.styles['BodyText'],
            fontSize=11,
            leading=16,
            backColor=colors.HexColor('#fff3cd'),
            borderWidth=2,
            borderColor=colors.HexColor('#ffc107'),
            borderPadding=10,
            leftIndent=10,
            rightIndent=10,
            spaceAfter=15
        ))
    
    def generate_pdf(self, report, screenshots=None, eli5_sections=None):
        """
        Generate PDF from WeeklyReport object.
        
        Args:
            report: WeeklyReport model instance
            screenshots: List of screenshot file paths
            eli5_sections: Dictionary of ELI5 explanations by section
        
        Returns:
            BytesIO: PDF file buffer
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
            title=report.subject,
            author=report.generated_by.get_full_name() if report.generated_by else 'System'
        )
        
        # Build document content
        story = []
        
        # Title page
        story.extend(self._create_title_page(report))
        story.append(PageBreak())
        
        # Table of contents
        story.extend(self._create_table_of_contents())
        story.append(PageBreak())
        
        # Executive Summary
        story.extend(self._create_section(
            'Executive Summary',
            report.executive_summary,
            eli5_sections.get('executive_summary') if eli5_sections else None
        ))
        
        # New Features
        story.extend(self._create_section(
            'New Features Implemented',
            report.new_features,
            eli5_sections.get('new_features') if eli5_sections else None,
            icon='✨'
        ))
        
        # Add screenshots if available
        if screenshots:
            story.extend(self._add_screenshots(screenshots, 'Feature Screenshots'))
        
        # Bug Fixes
        story.extend(self._create_section(
            'Bug Fixes and Issues Resolved',
            report.bug_fixes,
            eli5_sections.get('bug_fixes') if eli5_sections else None,
            icon='🐛'
        ))
        
        # Database Changes
        story.extend(self._create_section(
            'Database Changes',
            report.database_changes,
            eli5_sections.get('database_changes') if eli5_sections else None,
            icon='🗄️'
        ))
        
        # Code Improvements
        story.extend(self._create_section(
            'Code Improvements and Refactoring',
            report.code_improvements,
            eli5_sections.get('code_improvements') if eli5_sections else None,
            icon='⚡'
        ))
        
        # Pending Tasks
        story.extend(self._create_section(
            'Pending Tasks and Known Issues',
            report.pending_tasks,
            eli5_sections.get('pending_tasks') if eli5_sections else None,
            icon='📋'
        ))
        
        # Next Priorities
        story.extend(self._create_section(
            "Next Week's Priorities",
            report.next_priorities,
            eli5_sections.get('next_priorities') if eli5_sections else None,
            icon='🎯'
        ))
        
        # Custom Notes
        if report.custom_notes:
            story.extend(self._create_section(
                'Custom Notes',
                report.custom_notes,
                icon='📝'
            ))
        
        # Statistics
        story.append(PageBreak())
        story.extend(self._create_statistics_section(report))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    def _create_title_page(self, report):
        """Create title page elements."""
        elements = []
        
        # Title
        title = Paragraph(report.subject, self.styles['CustomTitle'])
        elements.append(Spacer(1, 1*inch))
        elements.append(title)
        elements.append(Spacer(1, 0.5*inch))
        
        # Date range
        date_range = f"{report.start_date.strftime('%B %d, %Y')} - {report.end_date.strftime('%B %d, %Y')}"
        date_para = Paragraph(
            f"<para alignment='center' fontSize='14' textColor='#7f8c8d'>{date_range}</para>",
            self.styles['CustomBody']
        )
        elements.append(date_para)
        elements.append(Spacer(1, 0.3*inch))
        
        # Report ID
        report_id = Paragraph(
            f"<para alignment='center' fontSize='12' textColor='#95a5a6'>Report ID: {report.report_id}</para>",
            self.styles['CustomBody']
        )
        elements.append(report_id)
        elements.append(Spacer(1, 1*inch))
        
        # Generated info
        generated_by = report.generated_by.get_full_name() if report.generated_by else 'System'
        generated_at = report.generated_at.strftime('%B %d, %Y at %I:%M %p')
        info = Paragraph(
            f"<para alignment='center' fontSize='11' textColor='#7f8c8d'>"
            f"Generated by: {generated_by}<br/>"
            f"Generated on: {generated_at}"
            f"</para>",
            self.styles['CustomBody']
        )
        elements.append(info)
        
        return elements
    
    def _create_table_of_contents(self):
        """Create table of contents."""
        elements = []
        
        title = Paragraph("Table of Contents", self.styles['SectionHeader'])
        elements.append(title)
        elements.append(Spacer(1, 0.2*inch))
        
        toc_items = [
            "Executive Summary",
            "New Features Implemented",
            "Bug Fixes and Issues Resolved",
            "Database Changes",
            "Code Improvements and Refactoring",
            "Pending Tasks and Known Issues",
            "Next Week's Priorities",
            "Statistics and Metrics"
        ]
        
        for i, item in enumerate(toc_items, 1):
            toc_para = Paragraph(
                f"<para fontSize='11'>{i}. {item}</para>",
                self.styles['CustomBody']
            )
            elements.append(toc_para)
            elements.append(Spacer(1, 0.1*inch))
        
        return elements
    
    def _create_section(self, title, content, eli5_text=None, icon=''):
        """Create a report section with optional ELI5 explanation."""
        elements = []
        
        # Section header
        header_text = f"{icon} {title}" if icon else title
        header = Paragraph(header_text, self.styles['SectionHeader'])
        elements.append(header)
        elements.append(Spacer(1, 0.1*inch))
        
        # ELI5 explanation (if provided)
        if eli5_text:
            eli5_title = Paragraph(
                "<b>🎓 Explain Like I'm 5 (ELI5):</b>",
                self.styles['SubsectionHeader']
            )
            elements.append(eli5_title)
            
            eli5_para = Paragraph(eli5_text, self.styles['ELI5'])
            elements.append(eli5_para)
            elements.append(Spacer(1, 0.15*inch))
            
            # Separator
            technical_header = Paragraph(
                "<b>📊 Technical Details:</b>",
                self.styles['SubsectionHeader']
            )
            elements.append(technical_header)
        
        # Content
        if content:
            # Split content into lines and format
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    elements.append(Spacer(1, 0.05*inch))
                    continue
                
                # Check if it's a bullet point
                if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                    line = line[1:].strip()
                    para = Paragraph(f"• {line}", self.styles['BulletPoint'])
                # Check if it's a code/technical line
                elif line.startswith('    ') or '`' in line:
                    line = line.replace('`', '')
                    para = Paragraph(line, self.styles['CodeBlock'])
                # Check if it's a bold header
                elif line.startswith('**') and line.endswith('**'):
                    line = line.strip('*')
                    para = Paragraph(f"<b>{line}</b>", self.styles['SubsectionHeader'])
                else:
                    para = Paragraph(line, self.styles['CustomBody'])
                
                elements.append(para)
        else:
            no_content = Paragraph(
                "<i>No information available for this section.</i>",
                self.styles['CustomBody']
            )
            elements.append(no_content)
        
        elements.append(Spacer(1, 0.3*inch))
        return elements
    
    def _add_screenshots(self, screenshots, section_title):
        """Add screenshots to the PDF."""
        elements = []
        
        header = Paragraph(f"📸 {section_title}", self.styles['SectionHeader'])
        elements.append(header)
        elements.append(Spacer(1, 0.1*inch))
        
        for i, screenshot_path in enumerate(screenshots, 1):
            if os.path.exists(screenshot_path):
                try:
                    # Add caption
                    caption = Paragraph(
                        f"<b>Screenshot {i}:</b> {os.path.basename(screenshot_path)}",
                        self.styles['SubsectionHeader']
                    )
                    elements.append(caption)
                    
                    # Add image (resize to fit page width)
                    img = Image(screenshot_path, width=6*inch, height=4*inch, kind='proportional')
                    elements.append(img)
                    elements.append(Spacer(1, 0.2*inch))
                    
                except Exception as e:
                    logger.warning(f"Could not add screenshot {screenshot_path}: {e}")
                    error_para = Paragraph(
                        f"<i>Could not load screenshot: {os.path.basename(screenshot_path)}</i>",
                        self.styles['CustomBody']
                    )
                    elements.append(error_para)
        
        elements.append(Spacer(1, 0.3*inch))
        return elements
    
    def _create_statistics_section(self, report):
        """Create statistics and metrics section."""
        elements = []
        
        header = Paragraph("📊 Statistics and Metrics", self.styles['SectionHeader'])
        elements.append(header)
        elements.append(Spacer(1, 0.1*inch))
        
        # Create statistics table
        data = [
            ['Metric', 'Value'],
            ['Commits Analyzed', str(report.commits_analyzed)],
            ['Files Scanned', str(report.files_scanned)],
            ['Migrations Found', str(report.migrations_found)],
            ['Report Generated', report.generated_at.strftime('%B %d, %Y at %I:%M %p')],
            ['Report Status', report.get_status_display()],
        ]
        
        if report.sent_at:
            data.append(['Email Sent', report.sent_at.strftime('%B %d, %Y at %I:%M %p')])
        
        table = Table(data, colWidths=[3*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Footer
        footer = Paragraph(
            f"<para alignment='center' fontSize='9' textColor='#95a5a6'>"
            f"This report was automatically generated by the MOEN IMS Weekly Report System<br/>"
            f"Report ID: {report.report_id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            f"</para>",
            self.styles['CustomBody']
        )
        elements.append(footer)
        
        return elements
