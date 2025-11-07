# Example Email Configuration for Weekly Reports
# Add these settings to your Django settings.py file

# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================

# Gmail Configuration (Most Common)
# ----------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-16-char-app-password'  # Get from https://myaccount.google.com/apppasswords
DEFAULT_FROM_EMAIL = 'MOEN IMS <your-email@gmail.com>'

# Outlook/Office 365 Configuration
# ---------------------------------
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.office365.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your-email@outlook.com'
# EMAIL_HOST_PASSWORD = 'your-password'
# DEFAULT_FROM_EMAIL = 'MOEN IMS <your-email@outlook.com>'

# Yahoo Configuration
# -------------------
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.mail.yahoo.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your-email@yahoo.com'
# EMAIL_HOST_PASSWORD = 'your-app-password'
# DEFAULT_FROM_EMAIL = 'MOEN IMS <your-email@yahoo.com>'

# Custom SMTP Server
# ------------------
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'mail.yourdomain.com'
# EMAIL_PORT = 587  # or 465 for SSL
# EMAIL_USE_TLS = True  # or EMAIL_USE_SSL = True for port 465
# EMAIL_HOST_USER = 'noreply@yourdomain.com'
# EMAIL_HOST_PASSWORD = 'your-password'
# DEFAULT_FROM_EMAIL = 'MOEN IMS <noreply@yourdomain.com>'

# Development/Testing (Console Backend - prints to console instead of sending)
# -----------------------------------------------------------------------------
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# =============================================================================
# WEEKLY REPORT CONFIGURATION
# =============================================================================

# Default recipients for weekly reports
WEEKLY_REPORT_RECIPIENTS = [
    'supervisor@example.com',
    'manager@example.com',
]

# Alternative: Use ADMINS setting
# ADMINS = [
#     ('Manager Name', 'manager@example.com'),
#     ('Supervisor Name', 'supervisor@example.com'),
# ]

# =============================================================================
# SECURITY BEST PRACTICES
# =============================================================================

# Option 1: Use Environment Variables (Recommended)
# --------------------------------------------------
import os

EMAIL_HOST_USER = os.environ.get('EMAIL_USER', 'default@example.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')

# Then set environment variables:
# Windows: set EMAIL_USER=your-email@gmail.com
# Linux/Mac: export EMAIL_USER=your-email@gmail.com

# Option 2: Use .env file with python-dotenv
# -------------------------------------------
# Install: pip install python-dotenv
# 
# from dotenv import load_dotenv
# import os
# 
# load_dotenv()
# 
# EMAIL_HOST_USER = os.getenv('EMAIL_USER')
# EMAIL_HOST_PASSWORD = os.getenv('EMAIL_PASSWORD')
#
# Create .env file in project root:
# EMAIL_USER=your-email@gmail.com
# EMAIL_PASSWORD=your-app-password
#
# Add .env to .gitignore!

# =============================================================================
# TESTING EMAIL CONFIGURATION
# =============================================================================

# Test in Django shell:
# python manage.py shell
# 
# >>> from django.core.mail import send_mail
# >>> send_mail(
# ...     'Test Email',
# ...     'This is a test email from Django.',
# ...     'your-email@gmail.com',
# ...     ['recipient@example.com'],
# ...     fail_silently=False,
# ... )
# 
# If you receive the email, configuration is correct!

# =============================================================================
# TROUBLESHOOTING
# =============================================================================

# Gmail "Less secure app access" error:
# - Use App Password instead of regular password
# - Enable 2-Factor Authentication
# - Generate App Password: https://myaccount.google.com/apppasswords

# Connection refused error:
# - Check firewall/antivirus blocking SMTP
# - Verify EMAIL_HOST and EMAIL_PORT
# - Try EMAIL_USE_SSL = True with port 465

# Authentication failed error:
# - Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
# - Check email provider's SMTP settings
# - Ensure account is active

# Timeout error:
# - Check internet connection
# - Verify SMTP server is accessible
# - Try different EMAIL_PORT (587 or 465)
