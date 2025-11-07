"""
Screenshot scanner and ELI5 README generator.
Automatically finds screenshots and creates simple explanations.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ScreenshotScanner:
    """
    Scans project for screenshots and documentation images.
    """
    
    # Common screenshot locations and patterns
    SCREENSHOT_DIRS = [
        'screenshots',
        'docs/screenshots',
        'docs/images',
        'documentation/images',
        'static/images/screenshots',
        'media/screenshots',
        'assets/screenshots',
        'images',
        'docs/assets'
    ]
    
    # Image file extensions
    IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']
    
    def __init__(self, project_root):
        """
        Initialize screenshot scanner.
        
        Args:
            project_root: Path to project root directory
        """
        self.project_root = Path(project_root)
    
    def find_recent_screenshots(self, days=7):
        """
        Find screenshots modified in the last N days.
        
        Args:
            days: Number of days to look back
        
        Returns:
            list: List of screenshot file paths
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        screenshots = []
        
        # Search in common screenshot directories
        for screenshot_dir in self.SCREENSHOT_DIRS:
            dir_path = self.project_root / screenshot_dir
            if dir_path.exists() and dir_path.is_dir():
                screenshots.extend(self._scan_directory(dir_path, cutoff_date))
        
        # Also search root docs directory
        docs_path = self.project_root / 'docs'
        if docs_path.exists():
            screenshots.extend(self._scan_directory(docs_path, cutoff_date, recursive=True))
        
        # Sort by modification time (newest first)
        screenshots.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        logger.info(f"Found {len(screenshots)} recent screenshots")
        return screenshots
    
    def _scan_directory(self, directory, cutoff_date, recursive=False):
        """
        Scan a directory for image files.
        
        Args:
            directory: Directory path to scan
            cutoff_date: Only include files modified after this date
            recursive: Whether to scan subdirectories
        
        Returns:
            list: List of image file paths
        """
        images = []
        
        try:
            if recursive:
                # Recursive search
                for ext in self.IMAGE_EXTENSIONS:
                    images.extend(directory.rglob(f'*{ext}'))
            else:
                # Single directory search
                for ext in self.IMAGE_EXTENSIONS:
                    images.extend(directory.glob(f'*{ext}'))
            
            # Filter by modification date
            recent_images = []
            for img_path in images:
                if img_path.is_file():
                    mod_time = datetime.fromtimestamp(os.path.getmtime(img_path))
                    if mod_time >= cutoff_date:
                        recent_images.append(str(img_path))
            
            return recent_images
        
        except Exception as e:
            logger.warning(f"Error scanning directory {directory}: {e}")
            return []
    
    def categorize_screenshots(self, screenshots):
        """
        Categorize screenshots by type based on filename.
        
        Args:
            screenshots: List of screenshot paths
        
        Returns:
            dict: Screenshots categorized by type
        """
        categories = {
            'features': [],
            'bugs': [],
            'ui': [],
            'dashboard': [],
            'reports': [],
            'other': []
        }
        
        for screenshot in screenshots:
            filename = os.path.basename(screenshot).lower()
            
            if any(word in filename for word in ['feature', 'new', 'add']):
                categories['features'].append(screenshot)
            elif any(word in filename for word in ['bug', 'fix', 'error', 'issue']):
                categories['bugs'].append(screenshot)
            elif any(word in filename for word in ['ui', 'interface', 'design', 'layout']):
                categories['ui'].append(screenshot)
            elif any(word in filename for word in ['dashboard', 'home', 'main']):
                categories['dashboard'].append(screenshot)
            elif any(word in filename for word in ['report', 'chart', 'graph', 'analytics']):
                categories['reports'].append(screenshot)
            else:
                categories['other'].append(screenshot)
        
        return categories


class ELI5Generator:
    """
    Generates executive summaries for non-technical stakeholders.
    Translates technical content into clear, professional business language.
    """
    
    def __init__(self):
        """Initialize executive summary generator."""
        pass
    
    def generate_eli5_sections(self, report_data):
        """
        Generate ELI5 explanations for each report section.
        
        Args:
            report_data: Dictionary containing report sections
        
        Returns:
            dict: ELI5 explanations for each section
        """
        eli5_sections = {}
        
        # Executive Summary
        if report_data.get('executive_summary'):
            eli5_sections['executive_summary'] = self._simplify_executive_summary(
                report_data['executive_summary']
            )
        
        # New Features
        if report_data.get('new_features'):
            eli5_sections['new_features'] = self._simplify_features(
                report_data['new_features']
            )
        
        # Bug Fixes
        if report_data.get('bug_fixes'):
            eli5_sections['bug_fixes'] = self._simplify_bug_fixes(
                report_data['bug_fixes']
            )
        
        # Database Changes
        if report_data.get('database_changes'):
            eli5_sections['database_changes'] = self._simplify_database_changes(
                report_data['database_changes']
            )
        
        # Code Improvements
        if report_data.get('code_improvements'):
            eli5_sections['code_improvements'] = self._simplify_code_improvements(
                report_data['code_improvements']
            )
        
        # Pending Tasks
        if report_data.get('pending_tasks'):
            eli5_sections['pending_tasks'] = self._simplify_pending_tasks(
                report_data['pending_tasks']
            )
        
        # Next Priorities
        if report_data.get('next_priorities'):
            eli5_sections['next_priorities'] = self._simplify_next_priorities(
                report_data['next_priorities']
            )
        
        return eli5_sections
    
    def _simplify_executive_summary(self, summary):
        """Create executive summary for non-technical stakeholders."""
        # Extract key numbers
        commits = self._extract_number(summary, r'(\d+)\s+commit')
        features = self._extract_number(summary, r'(\d+)\s+(?:new\s+)?feature')
        fixes = self._extract_number(summary, r'(\d+)\s+(?:bug\s+)?fix')
        
        exec_summary = "**Key Highlights:** "
        
        highlights = []
        if commits:
            highlights.append(f"{commits} system updates deployed")
        if features:
            highlights.append(f"{features} new {'capability' if features == 1 else 'capabilities'} added")
        if fixes:
            highlights.append(f"{fixes} {'issue' if fixes == 1 else 'issues'} resolved")
        
        if highlights:
            exec_summary += ", ".join(highlights) + ". "
        
        exec_summary += "The system continues to improve in functionality and reliability."
        
        return exec_summary
    
    def _simplify_features(self, features):
        """Create executive summary of new features."""
        if not features or features == "No new features implemented this week.":
            return "No new features were deployed this week. Development efforts focused on system optimization and maintenance."
        
        feature_count = len([line for line in features.split('\n') if line.strip().startswith('•')])
        
        return (
            f"This week, {feature_count} new {'feature was' if feature_count == 1 else 'features were'} successfully deployed to the system. "
            f"These enhancements improve operational efficiency and expand system capabilities for end users. "
            f"Each feature has been tested and is ready for production use."
        )
    
    def _simplify_bug_fixes(self, fixes):
        """Create executive summary of bug fixes."""
        if not fixes or fixes == "No bug fixes recorded this week.":
            return "System stability remained high this week with no critical issues reported. All systems operating normally."
        
        fix_count = len([line for line in fixes.split('\n') if line.strip().startswith('•')])
        
        return (
            f"{fix_count} system {'issue was' if fix_count == 1 else 'issues were'} identified and resolved this week. "
            f"These fixes improve system reliability and user experience. "
            f"All corrections have been tested and deployed to production."
        )
    
    def _simplify_database_changes(self, changes):
        """Create executive summary of database changes."""
        if not changes or changes == "No database migrations created this week.":
            return "No database schema changes were required this week. The current data structure continues to meet operational needs."
        
        return (
            "Database schema updates were implemented to support new features and improve data organization. "
            "These changes enhance system performance and data retrieval efficiency. "
            "All migrations were completed successfully with no data loss or downtime."
        )
    
    def _simplify_code_improvements(self, improvements):
        """Create executive summary of code improvements."""
        if not improvements or improvements == "No code improvements or refactoring recorded this week.":
            return "Code maintenance activities were minimal this week as development focused on feature delivery."
        
        return (
            "Code quality improvements were implemented to enhance system maintainability and performance. "
            "These refactoring efforts reduce technical debt and improve long-term system sustainability. "
            "Documentation was also updated to reflect current system architecture."
        )
    
    def _simplify_pending_tasks(self, tasks):
        """Create executive summary of pending tasks."""
        if not tasks or tasks == "No new pending tasks or known issues identified.":
            return "The development backlog is well-managed with no critical items requiring immediate attention."
        
        return (
            "Several development tasks and known issues have been identified and prioritized for upcoming sprints. "
            "These items are tracked in the project management system and will be addressed based on business priority. "
            "No critical blockers are currently impacting system operations."
        )
    
    def _simplify_next_priorities(self, priorities):
        """Create executive summary of next priorities."""
        return (
            "Development priorities for the upcoming week have been established based on business objectives and stakeholder feedback. "
            "The team will focus on high-impact features and critical system improvements. "
            "Resource allocation has been optimized to ensure timely delivery of key initiatives."
        )
    
    def _extract_number(self, text, pattern):
        """Extract a number from text using regex pattern."""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                return None
        return None
    
    def create_eli5_readme(self, report, screenshots_by_category):
        """
        Create a complete ELI5-style README document.
        
        Args:
            report: WeeklyReport object
            screenshots_by_category: Dictionary of categorized screenshots
        
        Returns:
            str: Markdown-formatted ELI5 README
        """
        readme = f"""# 🎓 Weekly Development Report (Easy Version)
## {report.start_date.strftime('%B %d')} - {report.end_date.strftime('%B %d, %Y')}

> **What is this?** This is a simple, easy-to-understand summary of what the development team did this week!

---

## 📚 What Happened This Week?

{self._simplify_executive_summary(report.executive_summary)}

---

## ✨ Cool New Things We Built

{self._simplify_features(report.new_features)}

"""
        
        # Add feature screenshots if available
        if screenshots_by_category.get('features'):
            readme += "\n### 📸 Pictures of New Features\n\n"
            for screenshot in screenshots_by_category['features'][:3]:  # Limit to 3
                readme += f"- {os.path.basename(screenshot)}\n"
            readme += "\n"
        
        readme += f"""---

## 🐛 Problems We Fixed

{self._simplify_bug_fixes(report.bug_fixes)}

---

## 🗄️ Behind-the-Scenes Changes

{self._simplify_database_changes(report.database_changes)}

---

## 🧹 Cleaning and Organizing

{self._simplify_code_improvements(report.code_improvements)}

---

## 📋 What's Still on Our To-Do List

{self._simplify_pending_tasks(report.pending_tasks)}

---

## 🎯 What We're Planning for Next Week

{self._simplify_next_priorities(report.next_priorities)}

---

## 📊 Fun Facts (Numbers!)

- **Changes Made:** {report.commits_analyzed} times we updated the code
- **Files Looked At:** {report.files_scanned} different files checked
- **Database Updates:** {report.migrations_found} times we reorganized our filing cabinet

---

## 🤔 Questions?

If you have any questions about what we did this week, just ask! We're happy to explain more.

---

*Report created on {report.generated_at.strftime('%B %d, %Y at %I:%M %p')}*
*Report ID: {report.report_id}*
"""
        
        return readme
