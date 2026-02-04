import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors

def create_workflow_pdf(input_md_path, output_pdf_path):
    # Constants for aesthetics
    PRIMARY_COLOR = colors.HexColor("#2563eb")
    SECONDARY_COLOR = colors.HexColor("#6b7280")
    
    # Setup document
    doc = SimpleDocTemplate(output_pdf_path, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=PRIMARY_COLOR,
        alignment=TA_CENTER,
        spaceAfter=30
    )
    
    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=PRIMARY_COLOR,
        spaceBefore=20,
        spaceAfter=15
    )
    
    subheading_style = ParagraphStyle(
        'SubheadingStyle',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=SECONDARY_COLOR,
        spaceBefore=10,
        spaceAfter=10
    )
    
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=10
    )

    story = []

    # Read the markdown file
    if not os.path.exists(input_md_path):
        print(f"Error: Input file {input_md_path} not found.")
        return

    with open(input_md_path, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 12))
            continue
            
        if line.startswith('# '):
            story.append(Paragraph(line[2:], title_style))
        elif line.startswith('## '):
            story.append(Paragraph(line[3:], heading_style))
        elif line.startswith('### '):
            story.append(Paragraph(line[4:], subheading_style))
        elif line.startswith('---'):
            story.append(Spacer(1, 12))
            story.append(Paragraph('<hr color="#e5e7eb" width="100%"/>', body_style))
            story.append(Spacer(1, 12))
        else:
            # Basic bullet point handling
            if line.startswith('* ') or line.startswith('- '):
                line = "• " + line[2:]
            
            # Simple bold/italic using regex
            import re
            line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
            line = re.sub(r'\*(.*?)\*', r'<i>\1</i>', line)
            
            story.append(Paragraph(line, body_style))

    doc.build(story)
    print(f"PDF generated successfully at {output_pdf_path}")

if __name__ == "__main__":
    input_path = "/home/leslie/.gemini/antigravity/brain/dd979ae8-d5f7-480d-8944-09b6e428d281/workflow_draft.md"
    output_path = "/home/leslie/Documents/GitHub/MOEN-IMS/MOEGT_IEPS_System_Workflows.pdf"
    create_workflow_pdf(input_path, output_path)
