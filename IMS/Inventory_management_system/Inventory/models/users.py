from django.db import models
import auto_prefetch
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.conf import settings
from django.core.validators import FileExtensionValidator
import uuid
import os
from .inventory import Warehouse

# Try to import PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class Profile(auto_prefetch.Model):
    """
    User profile model extending Django's built-in User model.
    Stores additional user information including profile picture and digital signature stamp.
    """
    user = auto_prefetch.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    signature_stamp = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Unique digital signature stamp for this user"
    )

    def __str__(self):
        """String representation of the profile."""
        if self.user:
            return f"{self.user.username} Profile"
        return "Profile (No User)"

    @property
    def profile_picture_url(self):
        """
        Returns the URL of the profile picture or a default image.
        
        Returns:
            str: URL path to the profile picture
        """
        if self.profile_picture:
            return self.profile_picture.url
        return '/static/images/default_profile.png'
    
    def generate_signature_stamp(self):
        """
        Generate a unique digital signature stamp for the user.
        The stamp includes: full name (first + last), timestamp, and a unique identifier.
        
        Format: "SIGNED_BY:{first_name} {last_name}|TIMESTAMP:{iso_timestamp}|ID:{unique_id}"
        
        Returns:
            str: The generated signature stamp
            
        Raises:
            ValueError: If user is None or has no name
        """
        if not self.user:
            raise ValueError("Cannot generate signature stamp: Profile has no associated user")
        
        # Get first and last name, fallback to username if names are not set
        first_name = self.user.first_name.strip() if self.user.first_name else ""
        last_name = self.user.last_name.strip() if self.user.last_name else ""
        
        # Construct full name
        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        elif first_name:
            full_name = first_name
        elif last_name:
            full_name = last_name
        elif hasattr(self.user, 'username') and self.user.username:
            # Fallback to username if no names are set
            full_name = self.user.username
        else:
            raise ValueError("Cannot generate signature stamp: User has no name or username")
        
        try:
            # Generate timestamp in ISO format
            timestamp = timezone.now().isoformat()
            
            # Generate unique identifier using UUID
            unique_id = uuid.uuid4().hex[:12].upper()
            
            # Create the signature stamp
            stamp = f"SIGNED_BY:{full_name}|TIMESTAMP:{timestamp}|ID:{unique_id}"
            
            return stamp
        except Exception as e:
            # Log the error and re-raise with context
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating signature stamp for user {full_name if 'full_name' in locals() else 'Unknown'}: {str(e)}")
            raise
    
    def get_or_create_signature_stamp(self):
        """
        Get existing signature stamp or create a new one if it doesn't exist.
        This method is safe to call multiple times and won't overwrite existing stamps.
        
        Returns:
            str: The signature stamp (existing or newly created)
        """
        if self.signature_stamp:
            return self.signature_stamp
        
        try:
            self.signature_stamp = self.generate_signature_stamp()
            self.save(update_fields=['signature_stamp'])
            return self.signature_stamp
        except ValueError as e:
            # Return a placeholder if we can't generate a stamp
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not generate signature stamp: {str(e)}")
            return None
    
    def display_signature_stamp(self):
        """
        Return a human-readable version of the signature stamp.
        
        Returns:
            dict: Parsed components of the signature stamp or None if no stamp exists
        """
        if not self.signature_stamp:
            return None
        
        try:
            # Parse the stamp components
            parts = self.signature_stamp.split('|')
            stamp_data = {}
            
            for part in parts:
                if ':' in part:
                    key, value = part.split(':', 1)
                    stamp_data[key] = value
            
            return stamp_data
        except Exception:
            return {'raw': self.signature_stamp}
    
    def regenerate_signature_stamp(self, force=False):
        """
        Regenerate the signature stamp. Use with caution as this will overwrite the existing stamp.
        
        Args:
            force (bool): If True, regenerate even if a stamp already exists
            
        Returns:
            str: The newly generated signature stamp
            
        Raises:
            ValueError: If force=False and a stamp already exists
        """
        if self.signature_stamp and not force:
            raise ValueError("Signature stamp already exists. Use force=True to regenerate.")
        
        self.signature_stamp = self.generate_signature_stamp()
        self.save(update_fields=['signature_stamp'])
        return self.signature_stamp
    
    def generate_digital_stamp_png(self):
        """
        Generate a PNG digital signature stamp image for the user.
        Creates a professional-looking stamp with user name, role, and unique ID.
        Saves to media/digital_signatures/ folder.
        
        Returns:
            str: Path to the generated PNG file, or None if generation failed
        """
        if not self.user:
            return None
        
        if not PIL_AVAILABLE:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PIL/Pillow not available. Cannot generate PNG stamps.")
            return None
        
        try:
            # Get user information
            full_name = self.user.get_full_name() or self.user.username
            username = self.user.username
            
            # Get user's role/group
            user_groups = self.user.groups.all()
            role = user_groups[0].name if user_groups.exists() else "User"
            
            # Get registration year
            registration_year = self.user.date_joined.year if self.user.date_joined else timezone.now().year
            
            # Generate unique ID (use existing signature_stamp ID if available, otherwise create new)
            unique_id = None
            if self.signature_stamp and 'ID:' in self.signature_stamp:
                try:
                    parts = self.signature_stamp.split('|')
                    for part in parts:
                        if 'ID:' in part:
                            unique_id = part.split('ID:')[1].strip()
                            break
                except Exception:
                    pass
            
            if not unique_id:
                unique_id = uuid.uuid4().hex[:12].upper()
            
            # Create digital_signatures directory if it doesn't exist
            digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
            if not os.path.exists(digital_signatures_dir):
                # Try with space in folder name
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                if not os.path.exists(digital_signatures_dir):
                    os.makedirs(digital_signatures_dir, exist_ok=True)
            
            # Create stamp image (300x150 pixels)
            width, height = 300, 150
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Draw border
            border_color = '#1a5490'  # Navy blue
            draw.rectangle([(0, 0), (width-1, height-1)], outline=border_color, width=3)
            
            # Draw inner border
            draw.rectangle([(5, 5), (width-6, height-6)], outline='#dc3545', width=2)
            
            # Try to use a nice font, fallback to default
            try:
                # Try to use system fonts
                if os.name == 'nt':  # Windows
                    title_font = ImageFont.truetype("arial.ttf", 14)
                    name_font = ImageFont.truetype("arial.ttf", 16)
                    text_font = ImageFont.truetype("arial.ttf", 10)
                else:  # Linux/Mac
                    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
                    name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                    text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            except:
                # Fallback to default font
                title_font = ImageFont.load_default()
                name_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
            
            # Helper function to get text width (works with both default and truetype fonts)
            def get_text_width(text, font):
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    return bbox[2] - bbox[0]
                except:
                    # Fallback for older PIL versions
                    try:
                        return draw.textlength(text, font=font)
                    except:
                        # Last resort: estimate width
                        return len(text) * 6
            
            # Draw "AUTHORIZED SIGNATURE" at top
            title_text = "AUTHORIZED SIGNATURE"
            title_width = get_text_width(title_text, title_font)
            draw.text(((width - title_width) / 2, 12), title_text, fill=border_color, font=title_font)
            
            # Draw user's full name (centered)
            name_width = get_text_width(full_name, name_font)
            draw.text(((width - name_width) / 2, 45), full_name, fill='black', font=name_font)
            
            # Draw role
            role_width = get_text_width(role, text_font)
            draw.text(((width - role_width) / 2, 70), role, fill='#666666', font=text_font)
            
            # Draw "Since YEAR" and "ID: XXXXXX" at bottom
            since_text = f"Since {registration_year}"
            id_text = f"ID: {unique_id}"
            
            since_width = get_text_width(since_text, text_font)
            id_width = get_text_width(id_text, text_font)
            
            draw.text((15, height - 30), since_text, fill='#666666', font=text_font)
            draw.text((width - id_width - 15, height - 30), id_text, fill='#666666', font=text_font)
            
            # Save the image
            filename = f"{username}.png"
            filepath = os.path.join(digital_signatures_dir, filename)
            img.save(filepath, 'PNG')
            
            return filepath
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating PNG digital stamp for user {self.user.username if self.user else 'Unknown'}: {str(e)}")
            return None


class WeeklyReport(auto_prefetch.Model):
    """
    Model to store generated weekly development reports.
    Keeps a history of all reports sent for auditing and reference.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    # Report metadata
    report_id = models.CharField(max_length=50, unique=True, editable=False, help_text="Unique report identifier")
    generated_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_reports')
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Date range
    start_date = models.DateField(help_text="Start date of the reporting period")
    end_date = models.DateField(help_text="End date of the reporting period")
    
    # Report content
    subject = models.CharField(max_length=500, help_text="Email subject line")
    executive_summary = models.TextField(help_text="Brief overview of the week's activities")
    new_features = models.TextField(blank=True, help_text="New features implemented")
    bug_fixes = models.TextField(blank=True, help_text="Bug fixes and issues resolved")
    database_changes = models.TextField(blank=True, help_text="Database migrations and schema changes")
    code_improvements = models.TextField(blank=True, help_text="Code refactoring and improvements")
    pending_tasks = models.TextField(blank=True, help_text="Pending tasks and known issues")
    next_priorities = models.TextField(blank=True, help_text="Next week's priorities")
    custom_notes = models.TextField(blank=True, help_text="Custom notes added by the generator")
    
    # Email details
    recipients = models.TextField(help_text="Comma-separated list of recipient emails")
    cc_recipients = models.TextField(blank=True, help_text="Comma-separated list of CC emails")
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sent_at = models.DateTimeField(null=True, blank=True, help_text="When the report was sent")
    error_message = models.TextField(blank=True, help_text="Error message if sending failed")
    
    # Statistics
    commits_analyzed = models.IntegerField(default=0, help_text="Number of git commits analyzed")
    files_scanned = models.IntegerField(default=0, help_text="Number of documentation files scanned")
    migrations_found = models.IntegerField(default=0, help_text="Number of migrations found")
    
    # Full report content (for archival)
    html_content = models.TextField(blank=True, help_text="Full HTML email content")
    plain_text_content = models.TextField(blank=True, help_text="Plain text email content")
    pdf_file = models.FileField(upload_to='weekly_reports/', blank=True, null=True, help_text="Generated PDF report")
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-generated_at']
        verbose_name = 'Weekly Report'
        verbose_name_plural = 'Weekly Reports'
    
    def __str__(self):
        return f"Weekly Report {self.report_id} - {self.start_date} to {self.end_date}"
    
    def save(self, *args, **kwargs):
        """Generate unique report ID if not set"""
        if not self.report_id:
            # Format: WR-YYYYMMDD-XXXX
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            random_suffix = str(uuid.uuid4())[:4].upper()
            self.report_id = f"WR-{date_str}-{random_suffix}"
        super().save(*args, **kwargs)
    
    def mark_as_sent(self):
        """Mark report as successfully sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.error_message = ''
        self.save()
    
    def mark_as_failed(self, error_message):
        """Mark report as failed with error message"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()
    
    def get_recipients_list(self):
        """Return list of recipient emails"""
        return [email.strip() for email in self.recipients.split(',') if email.strip()]
    
    def get_cc_recipients_list(self):
        """Return list of CC recipient emails"""
        if self.cc_recipients:
            return [email.strip() for email in self.cc_recipients.split(',') if email.strip()]
        return []


class ReportSubmission(auto_prefetch.Model):
    # Fields matching BillOfQuantity
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50)
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4)")
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200)
    contract_quantity = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    warehouse = auto_prefetch.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this report"
    )
    executive_summary = models.TextField(help_text="Provide a summary of the report")
    submission_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('Draft', 'Draft'),
            ('Submitted', 'Submitted'),
            ('Approved', 'Approved'),
            ('Rejected', 'Rejected')
        ],
        default='Draft'
    )
    
    # Add the new PDF field
    monthly_report = models.FileField(
        upload_to='monthly_reports/',
        help_text="Upload monthly report in PDF format",
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf'],
                message="Only PDF files are allowed"
            )
        ],
        null=True,
        blank=True
    )
    
    # Foreign keys
    user = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = auto_prefetch.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    related_boq = auto_prefetch.ForeignKey(
        'Inventory.BillOfQuantity', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='report_submissions'
    )

    class Meta(auto_prefetch.Model.Meta):
        verbose_name_plural = 'report submissions'

    def __str__(self):
        return f"Report for {self.package_number} - {self.submission_date.date()}"

    def create_or_update_boq(self):
        """
        Creates or updates a corresponding BillOfQuantity entry
        """
        # Local import to avoid circular dependency
        from .projects import BillOfQuantity
        
        if self.status == 'Approved':
            boq, created = BillOfQuantity.objects.get_or_create(
                package_number=self.package_number,
                item_code=self.item_code,
                defaults={
                    'region': self.region,
                    'district': self.district,
                    'consultant': self.consultant,
                    'contractor': self.contractor,
                    'material_description': self.material_description,
                    'contract_quantity': self.contract_quantity,
                    'quantity_received': self.quantity_received,
                    'phase': self.phase,
                    'user': self.user,
                    'group': self.group
                }
            )
            self.related_boq = boq
            self.save()

    @property
    def balance(self):
        """Calculate the remaining balance (contract_quantity - quantity_received)"""
        return self.contract_quantity - self.quantity_received


class Notification(auto_prefetch.Model):
    """
    Model for system notifications between user groups
    """
    NOTIFICATION_TYPES = [
        ('material_request', 'Material Request'),
        ('material_processed', 'Material Processed'),
        ('transport_assigned', 'Transport Assigned'),
        ('material_delivered', 'Material Delivered'),
        ('site_receipt_logged', 'Site Receipt Logged'),
        ('boq_updated', 'BOQ Updated'),
        ('staff_prompt', 'Staff Prompt'),
    ]
    
    RECIPIENT_GROUPS = [
        ('Schedule Officers', 'Schedule Officers'),
        ('Store Officers', 'Store Officers'),
        ('Management', 'Management'),
        ('Consultants', 'Consultants'),
        ('All', 'All Users'),
    ]
    
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Recipients
    recipient_group = models.CharField(max_length=20, choices=RECIPIENT_GROUPS)
    recipient_user = auto_prefetch.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='received_notifications',
        help_text="Specific user recipient (optional)"
    )
    
    # Sender
    sender = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    
    # Related objects (optional) - Using string references for circular dependencies
    related_order = auto_prefetch.ForeignKey(
        'Inventory.MaterialOrder',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_transport = auto_prefetch.ForeignKey(
        'Inventory.MaterialTransport',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_project = auto_prefetch.ForeignKey(
        'Inventory.Project',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.title} - {self.recipient_group}"
    
    def mark_as_read(self, user=None):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
