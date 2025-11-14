"""
Excel template generation utilities for user import.
"""

import pandas as pd
from django.http import HttpResponse
from io import BytesIO


def generate_user_import_template():
    """
    Generate a sample Excel template for user import.
    
    Returns:
        HttpResponse: Excel file download response
    """
    # Sample data
    sample_data = [
        {
            'username': 'john.doe',
            'name': 'John Doe',
            'email': 'john.doe@example.com'
        },
        {
            'username': 'jane.smith',
            'name': 'Jane Smith',
            'email': 'jane.smith@example.com'
        },
        {
            'username': 'mike.wilson',
            'name': 'Mike Wilson',
            'email': 'mike.wilson@example.com'
        },
        {
            'username': 'sarah.johnson',
            'name': 'Sarah Johnson',
            'email': 'sarah.johnson@example.com'
        },
        {
            'username': 'david.brown',
            'name': 'David Brown',
            'email': 'david.brown@example.com'
        }
    ]
    
    # Create DataFrame
    df = pd.DataFrame(sample_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Write sample data to 'Sample Data' sheet
        df.to_excel(writer, sheet_name='Sample Data', index=False)
        
        # Create empty template sheet
        empty_df = pd.DataFrame(columns=['username', 'name', 'email'])
        empty_df.to_excel(writer, sheet_name='Import Template', index=False)
        
        # Add instructions sheet
        instructions = [
            ['INSTRUCTIONS FOR USER IMPORT'],
            [''],
            ['1. Required Columns:'],
            ['   - username: Unique username for login (3+ characters)'],
            ['   - name: Full name of the user (will be split into first/last name)'],
            ['   - email: Valid email address (must be unique)'],
            [''],
            ['2. File Requirements:'],
            ['   - Excel format (.xlsx or .xls)'],
            ['   - Maximum file size: 10MB'],
            ['   - Maximum rows: 1000 users per import'],
            [''],
            ['3. Data Validation:'],
            ['   - Usernames must be unique across the system'],
            ['   - Email addresses must be valid and unique'],
            ['   - Names cannot be empty'],
            [''],
            ['4. Password Generation:'],
            ['   - Passwords are automatically generated (12 characters)'],
            ['   - Contains uppercase, lowercase, numbers, and special characters'],
            ['   - Passwords will be displayed after import - save them securely!'],
            [''],
            ['5. User Groups:'],
            ['   - You can optionally assign all imported users to a default group'],
            ['   - Groups can be managed in the Django admin interface'],
            [''],
            ['6. Import Process:'],
            ['   - Use the "Import Template" sheet for your data'],
            ['   - Delete the sample data before importing'],
            ['   - Review the "Sample Data" sheet for formatting examples'],
            [''],
            ['7. Security Notes:'],
            ['   - Only superusers can import users'],
            ['   - Generated passwords should be shared securely'],
            ['   - Users should change passwords on first login'],
        ]
        
        instructions_df = pd.DataFrame(instructions, columns=['Instructions'])
        instructions_df.to_excel(writer, sheet_name='Instructions', index=False, header=False)
    
    output.seek(0)
    
    # Create HTTP response
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="user_import_template.xlsx"'
    
    return response


def create_user_import_template_view(request):
    """
    Django view to download the user import template.
    """
    return generate_user_import_template()
