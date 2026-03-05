import pandas as pd
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging
import math

from .models.projects import Project, ProjectSite
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

class ExcelProjectSiteImporter:
    """
    Handles importing Project Sites from an Excel template.
    It automatically creates Projects if they do not exist based on the Project Code.
    """
    def __init__(self):
        self.import_results = {
            'success_count': 0,
            'error_count': 0,
            'errors': [],
            'warnings': []
        }

    def _get_string_val(self, val):
        if pd.isna(val) or val is None:
            return ""
        return str(val).strip()

    def _get_float_val(self, val):
        if pd.isna(val) or val is None:
            return None
        try:
            return float(val)
        except:
            return None

    def _get_date_val(self, val):
        if pd.isna(val) or val is None:
            return None
        # attempt to parse as date
        try:
            return pd.to_datetime(val).date()
        except:
            return None

    def import_from_excel(self, excel_file, user=None):
        logger.info("Starting Project Sites import from Excel")
        
        try:
            df = pd.read_excel(excel_file)
            df = df.dropna(how='all')
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_number = index + 2
                    
                    try:
                        project_code = self._get_string_val(row.get('Project Code'))
                        project_name = self._get_string_val(row.get('Project Name (Optional)', ''))
                        site_code = self._get_string_val(row.get('Site Code'))
                        site_name = self._get_string_val(row.get('Site Name'))
                        region = self._get_string_val(row.get('Region'))
                        district = self._get_string_val(row.get('District'))
                        community = self._get_string_val(row.get('Community'))
                        status = self._get_string_val(row.get('Status (Planned, Active, Completed, On Hold)'))
                        gps = self._get_string_val(row.get('GPS Coordinates'))
                        supervisor_username = self._get_string_val(row.get('Site Supervisor Username'))
                        start_date = self._get_date_val(row.get('Start Date (YYYY-MM-DD)'))
                        planned_completion = self._get_date_val(row.get('Planned Completion Date (YYYY-MM-DD)'))

                        if not project_code or not site_code or not site_name or not region or not district:
                            raise ValidationError("Missing one of the required fields: Project Code, Site Code, Site Name, Region, District.")

                        # Validate Status
                        valid_statuses = dict(ProjectSite.SITE_STATUS_CHOICES).keys()
                        if status and status not in valid_statuses:
                            status = 'Planned' # default fallback
                        elif not status:
                            status = 'Planned'

                        # Get or create Project
                        project, p_created = Project.objects.get_or_create(
                            code=project_code,
                            defaults={
                                'name': project_name if project_name else f"Project {project_code}",
                                'created_by': user
                            }
                        )

                        # Supervisor lookup
                        site_supervisor = None
                        if supervisor_username:
                            try:
                                site_supervisor = User.objects.get(username=supervisor_username)
                            except User.DoesNotExist:
                                self.import_results['warnings'].append(f"Row {row_number}: Supervisor '{supervisor_username}' not found. Leaving blank.")

                        # Create or update ProjectSite
                        site, s_created = ProjectSite.objects.update_or_create(
                            project=project,
                            code=site_code,
                            defaults={
                                'name': site_name,
                                'region': region,
                                'district': district,
                                'community': community,
                                'status': status,
                                'gps_coordinates': gps,
                                'site_supervisor': site_supervisor,
                                'start_date': start_date,
                                'planned_completion_date': planned_completion,
                            }
                        )
                        
                        self.import_results['success_count'] += 1
                        
                    except ValidationError as e:
                        error_messages = e.messages if hasattr(e, 'messages') else [str(e)]
                        for msg in error_messages:
                            self.import_results['errors'].append(f"Row {row_number}: {msg}")
                        self.import_results['error_count'] += 1
                    except Exception as e:
                        msg = f"Row {row_number}: Unexpected error - {str(e)}"
                        self.import_results['errors'].append(msg)
                        self.import_results['error_count'] += 1
                        logger.error(msg)
            
            return self.import_results

        except Exception as e:
            self.import_results['errors'].append(f"General Import Error: {str(e)}")
            self.import_results['error_count'] += 1
            return self.import_results
