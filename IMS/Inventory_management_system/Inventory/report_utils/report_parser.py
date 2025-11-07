"""
Documentation parser for weekly development reports.
Scans project files for documentation, commit messages, and code changes.
"""

import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentationParser:
    """
    Parses project documentation files to extract development information.
    """
    
    def __init__(self, project_root):
        """
        Initialize parser with project root directory.
        
        Args:
            project_root: Path to the project root directory
        """
        self.project_root = Path(project_root)
        self.scanned_files = 0
    
    def scan_readme_files(self):
        """
        Scan all README files in the project.
        
        Returns:
            list: List of dicts with file path and content
        """
        readme_files = []
        patterns = ['README.md', 'README.txt', 'README.rst', 'readme.md']
        
        try:
            for pattern in patterns:
                for readme_path in self.project_root.rglob(pattern):
                    try:
                        with open(readme_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            readme_files.append({
                                'path': str(readme_path.relative_to(self.project_root)),
                                'content': content,
                                'modified': datetime.fromtimestamp(readme_path.stat().st_mtime)
                            })
                            self.scanned_files += 1
                    except Exception as e:
                        logger.warning(f"Could not read {readme_path}: {e}")
        except Exception as e:
            logger.error(f"Error scanning README files: {e}")
        
        return readme_files
    
    def scan_changelog_files(self):
        """
        Scan CHANGELOG and similar files.
        
        Returns:
            list: List of dicts with file path and content
        """
        changelog_files = []
        patterns = ['CHANGELOG.md', 'CHANGES.md', 'HISTORY.md', 'changelog.md']
        
        try:
            for pattern in patterns:
                for changelog_path in self.project_root.rglob(pattern):
                    try:
                        with open(changelog_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            changelog_files.append({
                                'path': str(changelog_path.relative_to(self.project_root)),
                                'content': content,
                                'modified': datetime.fromtimestamp(changelog_path.stat().st_mtime)
                            })
                            self.scanned_files += 1
                    except Exception as e:
                        logger.warning(f"Could not read {changelog_path}: {e}")
        except Exception as e:
            logger.error(f"Error scanning CHANGELOG files: {e}")
        
        return changelog_files
    
    def scan_migration_files(self, days=7):
        """
        Scan Django migration files created in the last N days.
        
        Args:
            days: Number of days to look back
        
        Returns:
            list: List of migration file information
        """
        migrations = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            # Look for migrations directories
            for migrations_dir in self.project_root.rglob('migrations'):
                if migrations_dir.is_dir():
                    for migration_file in migrations_dir.glob('*.py'):
                        if migration_file.name == '__init__.py':
                            continue
                        
                        modified_time = datetime.fromtimestamp(migration_file.stat().st_mtime)
                        if modified_time >= cutoff_date:
                            try:
                                with open(migration_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    
                                    migrations.append({
                                        'path': str(migration_file.relative_to(self.project_root)),
                                        'name': migration_file.stem,
                                        'modified': modified_time,
                                        'content': content
                                    })
                                    self.scanned_files += 1
                            except Exception as e:
                                logger.warning(f"Could not read {migration_file}: {e}")
        except Exception as e:
            logger.error(f"Error scanning migration files: {e}")
        
        return migrations
    
    def scan_todo_fixme_comments(self, days=7):
        """
        Scan for TODO and FIXME comments in Python files.
        
        Args:
            days: Number of days to look back
        
        Returns:
            list: List of TODO/FIXME comments found
        """
        comments = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            for py_file in self.project_root.rglob('*.py'):
                # Skip virtual environments and migrations
                if 'venv' in str(py_file) or 'env' in str(py_file) or '__pycache__' in str(py_file):
                    continue
                
                modified_time = datetime.fromtimestamp(py_file.stat().st_mtime)
                if modified_time >= cutoff_date:
                    try:
                        with open(py_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                            # Find TODO and FIXME comments
                            todo_pattern = r'#\s*(TODO|FIXME|XXX|HACK|NOTE):\s*(.+)'
                            matches = re.finditer(todo_pattern, content, re.IGNORECASE)
                            
                            for match in matches:
                                comments.append({
                                    'file': str(py_file.relative_to(self.project_root)),
                                    'type': match.group(1).upper(),
                                    'comment': match.group(2).strip(),
                                    'modified': modified_time
                                })
                    except Exception as e:
                        logger.warning(f"Could not read {py_file}: {e}")
        except Exception as e:
            logger.error(f"Error scanning TODO/FIXME comments: {e}")
        
        return comments
    
    def extract_docstrings(self, file_path):
        """
        Extract docstrings from a Python file.
        
        Args:
            file_path: Path to Python file
        
        Returns:
            list: List of docstrings found
        """
        docstrings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Match triple-quoted docstrings
                docstring_pattern = r'"""(.*?)"""|\'\'\'(.*?)\'\'\''
                matches = re.finditer(docstring_pattern, content, re.DOTALL)
                
                for match in matches:
                    docstring = match.group(1) or match.group(2)
                    if docstring and len(docstring.strip()) > 20:  # Filter out short strings
                        docstrings.append(docstring.strip())
        except Exception as e:
            logger.warning(f"Could not extract docstrings from {file_path}: {e}")
        
        return docstrings


class GitAnalyzer:
    """
    Analyzes git commit history to extract development information.
    """
    
    def __init__(self, repo_path):
        """
        Initialize git analyzer.
        
        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        self.commits_analyzed = 0
    
    def get_commits(self, days=7):
        """
        Get git commits from the last N days.
        
        Args:
            days: Number of days to look back
        
        Returns:
            list: List of commit information
        """
        commits = []
        
        try:
            # Calculate date for git log
            since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Run git log command
            cmd = [
                'git', 'log',
                f'--since={since_date}',
                '--pretty=format:%H|%an|%ae|%ad|%s',
                '--date=iso'
            ]
            
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split('|')
                        if len(parts) >= 5:
                            commits.append({
                                'hash': parts[0],
                                'author': parts[1],
                                'email': parts[2],
                                'date': parts[3],
                                'message': '|'.join(parts[4:])  # In case message contains |
                            })
                            self.commits_analyzed += 1
            else:
                logger.warning(f"Git log failed: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            logger.error("Git log command timed out")
        except FileNotFoundError:
            logger.error("Git command not found. Make sure git is installed and in PATH")
        except Exception as e:
            logger.error(f"Error getting git commits: {e}")
        
        return commits
    
    def get_commit_stats(self, days=7):
        """
        Get statistics about commits (files changed, insertions, deletions).
        
        Args:
            days: Number of days to look back
        
        Returns:
            dict: Statistics about commits
        """
        stats = {
            'total_commits': 0,
            'files_changed': 0,
            'insertions': 0,
            'deletions': 0
        }
        
        try:
            since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Get commit count
            cmd_count = ['git', 'rev-list', '--count', f'--since={since_date}', 'HEAD']
            result = subprocess.run(cmd_count, cwd=self.repo_path, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                stats['total_commits'] = int(result.stdout.strip() or 0)
            
            # Get file changes
            cmd_stats = ['git', 'log', f'--since={since_date}', '--numstat', '--pretty=format:']
            result = subprocess.run(cmd_stats, cwd=self.repo_path, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                insertions = int(parts[0]) if parts[0] != '-' else 0
                                deletions = int(parts[1]) if parts[1] != '-' else 0
                                stats['insertions'] += insertions
                                stats['deletions'] += deletions
                                stats['files_changed'] += 1
                            except ValueError:
                                continue
        
        except Exception as e:
            logger.error(f"Error getting commit stats: {e}")
        
        return stats
    
    def categorize_commits(self, commits):
        """
        Categorize commits into features, fixes, refactoring, etc.
        
        Args:
            commits: List of commit dicts
        
        Returns:
            dict: Categorized commits
        """
        categories = {
            'features': [],
            'fixes': [],
            'refactoring': [],
            'documentation': [],
            'other': []
        }
        
        # Keywords for categorization
        feature_keywords = ['add', 'implement', 'create', 'new', 'feature']
        fix_keywords = ['fix', 'bug', 'issue', 'resolve', 'patch']
        refactor_keywords = ['refactor', 'improve', 'optimize', 'clean', 'update']
        doc_keywords = ['doc', 'documentation', 'readme', 'comment']
        
        for commit in commits:
            message = commit['message'].lower()
            categorized = False
            
            # Check for features
            if any(keyword in message for keyword in feature_keywords):
                categories['features'].append(commit)
                categorized = True
            
            # Check for fixes
            elif any(keyword in message for keyword in fix_keywords):
                categories['fixes'].append(commit)
                categorized = True
            
            # Check for refactoring
            elif any(keyword in message for keyword in refactor_keywords):
                categories['refactoring'].append(commit)
                categorized = True
            
            # Check for documentation
            elif any(keyword in message for keyword in doc_keywords):
                categories['documentation'].append(commit)
                categorized = True
            
            # Everything else
            if not categorized:
                categories['other'].append(commit)
        
        return categories

