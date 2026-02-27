import os
import re

TEMPLATE_DIR = r'c:\Users\Nii\Documents\GitHub\MOEN-IMS\IMS\Inventory_management_system\Inventory\templates'

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    errors = []
    
    # Regex for page_splash block
    # Matches {% block page_splash %} with flexible whitespace
    splash_matches = re.findall(r'{%\s*block\s+page_splash\s*%}', content)
    if len(splash_matches) > 1:
        errors.append(f"Duplicate 'page_splash' block found: {len(splash_matches)} times")

    # Regex for content block
    content_matches = re.findall(r'{%\s*block\s+content\s*%}', content)
    if len(content_matches) > 1:
        errors.append(f"Duplicate 'content' block found: {len(content_matches)} times")

    # Check for bad if/elif tag syntax: == without spaces
    # We want to find: {%\s*(if|elif) ... [^ ]== ... %} OR {%\s*(if|elif) ... ==[^ ] ... %}
    # breaking it down to line by line for easier reporting
    lines = content.split('\n')
    for i, line in enumerate(lines):
        # fast check
        if '{%' in line and ('if ' in line or 'elif ' in line) and '==' in line:
            # Extract the tag content
            tags = re.findall(r'{%(.*?)%}', line)
            for tag in tags:
                tag = tag.strip()
                if tag.startswith('if ') or tag.startswith('elif '):
                    # check for == issue in this tag
                    # match == not preceded by space AND not at start (which is impossible for ==)
                    # OR == not followed by space
                    # But be careful of string literals? Assuming standard simple conditions for now.
                    if re.search(r'[^ ]==|==[^ ]', tag):
                        errors.append(f"Line {i+1}: Potential syntax error in if/elif tag (missing spaces around ==): {line.strip()}")

    return errors

def main():
    print(f"Scanning templates in {TEMPLATE_DIR} (Regex Enhanced)...")
    issues_found = False
    for root, dirs, files in os.walk(TEMPLATE_DIR):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                errors = scan_file(path)
                if errors:
                    issues_found = True
                    print(f"\nFile: {path}")
                    for err in errors:
                        print(f"  - {err}")
    
    if not issues_found:
        print("\nNo obvious template errors found.")

if __name__ == '__main__':
    main()
