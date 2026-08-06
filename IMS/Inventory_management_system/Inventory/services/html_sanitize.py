"""
Allowlist sanitiser for officer-edited document HTML.

The WYSIWYG document editor posts back whatever `contenteditable` produced. That
HTML is re-rendered in a same-origin `<iframe>` on the release-letter detail
page, so anything we store unfiltered is a stored-XSS vector — WeasyPrint itself
ignores scripts, but the browser preview does not.

Rather than add a dependency, this is a small allowlist pass over Python's
stdlib `HTMLParser`:

  * only tags in ALLOWED_TAGS survive; everything else is dropped but its text
    content is kept (so a pasted `<div>` degrades to its words, not to nothing);
  * `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>` are dropped
    *including* their contents;
  * only attributes in ALLOWED_ATTRS survive, so every `on*` handler goes;
  * `src`/`href` must be http(s), mailto, or a `data:image/` URI — this is what
    keeps `javascript:` out while still allowing the inline letterhead/QR images;
  * `style` is filtered to a handful of harmless formatting declarations, which
    blocks `expression()`/`url()` tricks while letting the editor's own
    bold/italic/alignment output through.

Deliberately conservative: it is easier to add a tag when someone misses one
than to explain a document that executed script in an officer's browser.
"""

from html.parser import HTMLParser
from html import escape

# Structural + inline formatting the document templates and the editor produce.
ALLOWED_TAGS = {
    'p', 'div', 'span', 'br', 'hr',
    'b', 'strong', 'i', 'em', 'u', 's', 'sub', 'sup', 'small',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
    'colgroup', 'col',
    'img', 'a',
}

# Tags whose *contents* must die with them, not degrade to text.
VOID_CONTENT_TAGS = {'script', 'style', 'iframe', 'object', 'embed', 'template', 'noscript'}

SELF_CLOSING = {'br', 'hr', 'img', 'col'}

ALLOWED_ATTRS = {
    '*': {'class', 'style', 'colspan', 'rowspan', 'align', 'valign', 'id'},
    'img': {'src', 'alt', 'width', 'height'},
    'a': {'href', 'title', 'target', 'rel'},
    'col': {'span', 'width'},
    'table': {'border', 'cellpadding', 'cellspacing', 'width'},
}

# CSS declarations the editor legitimately emits. Anything else is discarded.
ALLOWED_CSS_PROPS = {
    'text-align', 'font-weight', 'font-style', 'text-decoration', 'font-size',
    'font-family', 'color', 'background-color', 'margin', 'margin-top',
    'margin-bottom', 'margin-left', 'margin-right', 'padding', 'padding-top',
    'padding-bottom', 'padding-left', 'padding-right', 'width', 'height',
    'border', 'border-bottom', 'border-top', 'border-collapse', 'vertical-align',
    'line-height', 'letter-spacing', 'text-transform', 'white-space', 'float',
    'clear', 'display', 'max-width', 'min-height', 'list-style-type',
}

_SAFE_URL_PREFIXES = ('http://', 'https://', 'mailto:', '/', '#')


def _safe_url(value):
    v = (value or '').strip()
    lowered = v.lower().replace('\t', '').replace('\n', '').replace('\r', '')
    if lowered.startswith('data:image/'):
        return v          # inline letterhead / QR images
    if lowered.startswith(_SAFE_URL_PREFIXES):
        return v
    return None           # javascript:, vbscript:, data:text/html, ...


def _safe_style(value):
    out = []
    for decl in (value or '').split(';'):
        if ':' not in decl:
            continue
        prop, _, val = decl.partition(':')
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in ALLOWED_CSS_PROPS:
            continue
        low = val.lower()
        if 'url(' in low or 'expression' in low or 'javascript:' in low or '@import' in low:
            continue
        out.append(f"{prop}: {val}")
    return '; '.join(out)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._suppress_depth = 0     # inside a drop-contents tag
        self._open = []              # allowed tags we have emitted, for closing

    # -- helpers ---------------------------------------------------------
    def _attrs(self, tag, attrs):
        allowed = ALLOWED_ATTRS.get('*', set()) | ALLOWED_ATTRS.get(tag, set())
        out = []
        for name, value in attrs:
            name = (name or '').lower()
            if name.startswith('on') or name not in allowed:
                continue
            if value is None:
                continue
            if name in ('src', 'href'):
                value = _safe_url(value)
                if value is None:
                    continue
            elif name == 'style':
                value = _safe_style(value)
                if not value:
                    continue
            out.append(f' {name}="{escape(value, quote=True)}"')
        return ''.join(out)

    # -- parser hooks ----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in VOID_CONTENT_TAGS:
            self._suppress_depth += 1
            return
        if self._suppress_depth or tag not in ALLOWED_TAGS:
            return
        if tag in SELF_CLOSING:
            self.parts.append(f"<{tag}{self._attrs(tag, attrs)}>")
        else:
            self.parts.append(f"<{tag}{self._attrs(tag, attrs)}>")
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._suppress_depth or tag in VOID_CONTENT_TAGS or tag not in ALLOWED_TAGS:
            return
        self.parts.append(f"<{tag}{self._attrs(tag, attrs)}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID_CONTENT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            return
        if self._suppress_depth or tag not in ALLOWED_TAGS or tag in SELF_CLOSING:
            return
        if tag in self._open:
            # Close everything opened after it too — contenteditable output is
            # not always well nested and WeasyPrint is stricter than a browser.
            while self._open:
                open_tag = self._open.pop()
                self.parts.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self._suppress_depth:
            return
        self.parts.append(escape(data, quote=False))

    def handle_comment(self, data):
        pass  # comments carry nothing we need and can hide conditional markup

    def result(self):
        while self._open:
            self.parts.append(f"</{self._open.pop()}>")
        return ''.join(self.parts)


def sanitize_document_html(raw, max_length=400_000):
    """Return `raw` reduced to the allowlist. Empty string for empty input.

    `max_length` is a cheap belt-and-braces cap — an edited release document is
    a few KB; anything approaching 400 KB is a paste accident or an attack, and
    both are better truncated than stored.
    """
    if not raw:
        return ''
    raw = str(raw)[:max_length]
    parser = _Sanitizer()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:  # noqa: BLE001 — malformed input must never 500 a save
        return ''
    return parser.result().strip()
