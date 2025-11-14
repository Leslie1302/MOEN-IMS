"""
User Import Module for Excel-based bulk user creation.

This module provides functionality to import users from Excel files with
automatic password generation and email notifications.
"""

import pandas as pd
import secrets
import string
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class UserImportError(Exception):
    """Custom exception for user import errors"""
    pass


class ExcelUserImporter:
    """
    Handles importing users from Excel files with automatic password generation.
    
    Expected Excel format:
    - Column headers: username, name, email
    - Each row represents a user to be created
    """
    
    REQUIRED_COLUMNS = ['username', 'name', 'email']
    PASSWORD_LENGTH = 12
    
    def __init__(self):
        self.import_results = {
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 0,
            'created_users': [],
            'errors': [],
            'warnings': []
        }
    
    def generate_secure_password(self, length: int = None) -> str:
        """
        Generate a secure random password.
        
        Args:
            length: Password length (default: 12)
            
        Returns:
            str: Secure random password
        """
        if length is None:
            length = self.PASSWORD_LENGTH
            
        # Define character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special_chars = "!@#$%^&*"
        
        # Ensure at least one character from each set
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special_chars)
        ]
        
        # Fill remaining length with random characters from all sets
        all_chars = lowercase + uppercase + digits + special_chars
        for _ in range(length - 4):
            password.append(secrets.choice(all_chars))
        
        # Shuffle the password list
        secrets.SystemRandom().shuffle(password)
        
        return ''.join(password)
    
    def validate_excel_file(self, file_path: str) -> pd.DataFrame:
        """
        Validate and read Excel file.
        
        Args:
            file_path: Path to Excel file
            
        Returns:
            pd.DataFrame: Validated DataFrame
            
        Raises:
            UserImportError: If file is invalid
        """
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            
            # Check if file is empty
            if df.empty:
                raise UserImportError("Excel file is empty")
            
            # Check for required columns
            missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_columns:
                raise UserImportError(f"Missing required columns: {', '.join(missing_columns)}")
            
            # Remove rows with all NaN values
            df = df.dropna(how='all')
            
            # Check if any data remains after cleaning
            if df.empty:
                raise UserImportError("No valid data found in Excel file")
            
            return df
            
        except Exception as e:
            if isinstance(e, UserImportError):
                raise
            raise UserImportError(f"Error reading Excel file: {str(e)}")
    
    def validate_user_data(self, row: pd.Series, row_number: int) -> Dict[str, str]:
        """
        Validate individual user data from Excel row.
        
        Args:
            row: Pandas Series representing a row
            row_number: Row number for error reporting
            
        Returns:
            dict: Validated user data
            
        Raises:
            ValidationError: If data is invalid
        """
        errors = []
        
        # Extract and clean data
        username = str(row.get('username', '')).strip()
        name = str(row.get('name', '')).strip()
        email = str(row.get('email', '')).strip()
        
        # Validate username
        if not username or username == 'nan':
            errors.append(f"Row {row_number}: Username is required")
        elif len(username) < 3:
            errors.append(f"Row {row_number}: Username must be at least 3 characters")
        elif User.objects.filter(username=username).exists():
            errors.append(f"Row {row_number}: Username '{username}' already exists")
        
        # Validate name
        if not name or name == 'nan':
            errors.append(f"Row {row_number}: Name is required")
        
        # Validate email
        if not email or email == 'nan':
            errors.append(f"Row {row_number}: Email is required")
        else:
            try:
                validate_email(email)
                if User.objects.filter(email=email).exists():
                    errors.append(f"Row {row_number}: Email '{email}' already exists")
            except ValidationError:
                errors.append(f"Row {row_number}: Invalid email format '{email}'")
        
        if errors:
            raise ValidationError(errors)
        
        # Split name into first and last name
        name_parts = name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        return {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'email': email
        }
    
    def create_user_with_password(self, user_data: Dict[str, str]) -> Tuple[User, str]:
        """
        Create a new user with generated password.
        
        Args:
            user_data: Dictionary containing user information
            
        Returns:
            tuple: (User object, generated password)
        """
        password = self.generate_secure_password()
        
        user = User.objects.create_user(
            username=user_data['username'],
            email=user_data['email'],
            password=password,
            first_name=user_data['first_name'],
            last_name=user_data['last_name']
        )
        
        # Create profile if it doesn't exist
        from .models import Profile
        profile, created = Profile.objects.get_or_create(user=user)
        if created:
            try:
                profile.get_or_create_signature_stamp()
            except Exception as e:
                logger.warning(f"Could not create signature stamp for user {user.username}: {str(e)}")
        
        return user, password
    
    def assign_default_group(self, user: User, default_group_name: str = 'default') -> None:
        """
        Assign user to default group if it exists.
        
        Args:
            user: User object
            default_group_name: Name of default group
        """
        try:
            default_group = Group.objects.get(name=default_group_name)
            user.groups.add(default_group)
            logger.info(f"Assigned user {user.username} to group {default_group_name}")
        except Group.DoesNotExist:
            logger.warning(f"Default group '{default_group_name}' does not exist")
    
    def import_users_from_excel(self, file_path: str, default_group: str = None) -> Dict:
        """
        Import users from Excel file.
        
        Args:
            file_path: Path to Excel file
            default_group: Optional default group to assign users to
            
        Returns:
            dict: Import results summary
        """
        logger.info(f"Starting user import from {file_path}")
        
        try:
            # Validate and read Excel file
            df = self.validate_excel_file(file_path)
            
            # Process each row
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_number = index + 2  # +2 because Excel is 1-indexed and has header
                    
                    try:
                        # Validate user data
                        user_data = self.validate_user_data(row, row_number)
                        
                        # Create user with password
                        user, password = self.create_user_with_password(user_data)
                        
                        # Assign to default group if specified
                        if default_group:
                            self.assign_default_group(user, default_group)
                        
                        # Record success
                        self.import_results['created_users'].append({
                            'user': user,
                            'password': password,
                            'username': user.username,
                            'email': user.email,
                            'name': f"{user.first_name} {user.last_name}".strip()
                        })
                        self.import_results['success_count'] += 1
                        
                        logger.info(f"Successfully created user: {user.username}")
                        
                    except ValidationError as e:
                        # Record validation errors
                        error_messages = e.messages if hasattr(e, 'messages') else [str(e)]
                        for error_msg in error_messages:
                            self.import_results['errors'].append(error_msg)
                        self.import_results['error_count'] += 1
                        
                    except Exception as e:
                        # Record unexpected errors
                        error_msg = f"Row {row_number}: Unexpected error - {str(e)}"
                        self.import_results['errors'].append(error_msg)
                        self.import_results['error_count'] += 1
                        logger.error(error_msg)
            
            # Add summary to results
            self.import_results['summary'] = (
                f"Import completed: {self.import_results['success_count']} users created, "
                f"{self.import_results['error_count']} errors encountered"
            )
            
            logger.info(self.import_results['summary'])
            return self.import_results
            
        except UserImportError as e:
            error_msg = f"Import failed: {str(e)}"
            self.import_results['errors'].append(error_msg)
            self.import_results['error_count'] += 1
            logger.error(error_msg)
            return self.import_results
        
        except Exception as e:
            error_msg = f"Unexpected error during import: {str(e)}"
            self.import_results['errors'].append(error_msg)
            self.import_results['error_count'] += 1
            logger.error(error_msg)
            return self.import_results
    
    def generate_import_report(self) -> str:
        """
        Generate a detailed import report.
        
        Returns:
            str: Formatted import report
        """
        report_lines = [
            "=== USER IMPORT REPORT ===",
            f"Import Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "SUMMARY:",
            f"  Successfully Created: {self.import_results['success_count']} users",
            f"  Errors: {self.import_results['error_count']}",
            f"  Skipped: {self.import_results['skipped_count']}",
            ""
        ]
        
        # Add created users details
        if self.import_results['created_users']:
            report_lines.extend([
                "CREATED USERS:",
                "Username | Name | Email | Password"
            ])
            for user_info in self.import_results['created_users']:
                report_lines.append(
                    f"{user_info['username']} | {user_info['name']} | "
                    f"{user_info['email']} | {user_info['password']}"
                )
            report_lines.append("")
        
        # Add errors
        if self.import_results['errors']:
            report_lines.extend(["ERRORS:"] + self.import_results['errors'] + [""])
        
        # Add warnings
        if self.import_results['warnings']:
            report_lines.extend(["WARNINGS:"] + self.import_results['warnings'] + [""])
        
        return "\n".join(report_lines)


def import_users_from_excel_file(file_path: str, default_group: str = None) -> Dict:
    """
    Convenience function to import users from Excel file.
    
    Args:
        file_path: Path to Excel file
        default_group: Optional default group name
        
    Returns:
        dict: Import results
    """
    importer = ExcelUserImporter()
    return importer.import_users_from_excel(file_path, default_group)
