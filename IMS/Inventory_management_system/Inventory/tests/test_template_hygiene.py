"""Static checks over every template in the app.

Django's `{# #}` comment is SINGLE-LINE ONLY — its lexer regex has no DOTALL
flag. A multi-line one is not recognised as a comment, and the consequences
range from bad to worse:

  * the comment text renders as visible content in the page or document;
  * if the comment happens to contain `{% ... %}`, the lexer instead matches
    that inner tag and Django raises TemplateSyntaxError at render time.

Both are invisible in code review and neither is caught by any view test that
doesn't happen to render the offending template. Hence a sweep.
"""

import glob
import os
import re

from django.conf import settings
from django.test import SimpleTestCase


def _template_files():
    roots = [os.path.join(str(settings.BASE_DIR), 'Inventory', 'templates')]
    for engine in getattr(settings, 'TEMPLATES', []):
        roots.extend(str(d) for d in engine.get('DIRS', []))
    files = []
    for root in roots:
        if os.path.isdir(root):
            files.extend(glob.glob(os.path.join(root, '**', '*.html'), recursive=True))
    return sorted(set(files))


class TemplateCommentHygieneTests(SimpleTestCase):
    def test_templates_exist_to_check(self):
        self.assertTrue(_template_files(), "no templates found — the sweep would pass vacuously")

    def test_no_multiline_django_comments(self):
        offenders = []
        for path in _template_files():
            with open(path, encoding='utf-8', errors='replace') as fh:
                source = fh.read()
            index = 0
            while True:
                start = source.find('{#', index)
                if start == -1:
                    break
                end = source.find('#}', start + 2)
                if end == -1:
                    offenders.append(f"{path}: unclosed {{# at line {source[:start].count(chr(10)) + 1}")
                    break
                chunk = source[start:end + 2]
                if '\n' in chunk:
                    line = source[:start].count('\n') + 1
                    offenders.append(
                        f"{os.path.relpath(path)}:{line} spans {chunk.count(chr(10)) + 1} lines"
                        + (" AND contains a {% %} tag — this raises TemplateSyntaxError"
                           if re.search(r'\{%.*?%\}', chunk, re.DOTALL) else ""))
                index = end + 2

        self.assertEqual(
            offenders, [],
            "Multi-line {# #} comments found. Django's {# #} is single-line only — "
            "use {% comment %}...{% endcomment %} instead:\n  " + "\n  ".join(offenders))

    def test_block_tags_are_balanced(self):
        """A stray {% endif %}/{% endwith %} is a render-time 500, not an import error."""
        paired = ('if', 'for', 'with', 'block', 'comment', 'autoescape', 'spaceless')
        offenders = []
        for path in _template_files():
            with open(path, encoding='utf-8', errors='replace') as fh:
                source = fh.read()
            counts = dict.fromkeys(paired, 0)
            for tag in re.findall(r'\{%\s*(\w+)', source):
                if tag in counts:
                    counts[tag] += 1
                elif tag.startswith('end') and tag[3:] in counts:
                    counts[tag[3:]] -= 1
            unbalanced = {k: v for k, v in counts.items() if v}
            if unbalanced:
                offenders.append(f"{os.path.relpath(path)}: {unbalanced}")

        self.assertEqual(offenders, [],
                         "Unbalanced template block tags:\n  " + "\n  ".join(offenders))
