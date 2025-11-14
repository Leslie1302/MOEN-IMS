#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script to automatically resolve git merge conflicts by keeping the 'theirs' version."""

import re

def fix_merge_conflicts(filepath):
    """Remove merge conflict markers and keep the 'theirs' version (after =======)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match entire conflict blocks
    # <<<<<<< Updated upstream
    # ... (ours - discard)
    # =======
    # ... (theirs - keep)
    # >>>>>>> Stashed changes
    
    pattern = r'<<<<<<< Updated upstream\n(.*?)\n=======\n(.*?)\n>>>>>>> Stashed changes'
    
    # Replace conflicts with the 'theirs' version (group 2)
    fixed_content = re.sub(pattern, r'\2', content, flags=re.DOTALL)
    
    # Also handle nested conflicts
    fixed_content = re.sub(r'<<<<<<< Updated upstream\n', '', fixed_content)
    fixed_content = re.sub(r'=======\n', '', fixed_content)
    fixed_content = re.sub(r'>>>>>>> Stashed changes\n?', '', fixed_content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"Fixed conflicts in {filepath}")

# Fix navigation.html
fix_merge_conflicts('Inventory/templates/Inventory/navigation.html')
print("All conflicts resolved!")
