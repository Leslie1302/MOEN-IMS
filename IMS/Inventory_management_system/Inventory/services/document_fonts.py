"""
Fonts that ship with the application, registered with WeasyPrint via @font-face.

The problem this solves: WeasyPrint can only use fonts installed on the render
host. Offering an officer a font the Azure box doesn't have produces a PDF that
silently falls back to something else — the document looks wrong and nobody can
say why. Installing fonts on App Service is worse still, because the filesystem
is rebuilt on every restart.

So fonts travel with the code. Drop a TTF/OTF into `Inventory/static/Inventory/
fonts/` and it is registered automatically: this module emits `@font-face` rules
pointing at absolute `file://` paths, which WeasyPrint resolves at render time.
Nothing to install, nothing for the server admin to do, and it survives restarts.

Filename convention (case-insensitive), so weights and italics group correctly:

    Tahoma.ttf              -> Tahoma, normal, normal
    Tahoma-Bold.ttf         -> Tahoma, bold, normal
    Tahoma-Italic.ttf       -> Tahoma, normal, italic
    Tahoma-BoldItalic.ttf   -> Tahoma, bold, italic

A family is only offered in the editor's font menu if at least its regular face
is present, so the menu can never list a font that will not actually render.

LICENSING: Tahoma, Calibri and the other Microsoft core fonts are licensed, not
freely redistributable. Confirm the Ministry's licence covers deploying the file
before committing one. Metric-compatible, freely licensed substitutes exist
(Wine's Tahoma replacement in `fonts-wine`; Carlito for Calibri; Liberation Sans
for Arial) if that is easier than a licence review.
"""

import logging
import os
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

FONT_EXTENSIONS = ('.ttf', '.otf', '.woff', '.woff2')

# Families the editor may offer, in menu order. A family absent from disk is
# simply not offered — see `available_families`.
KNOWN_FAMILIES = ('Tahoma', 'Arial', 'Calibri', 'Times New Roman', 'Georgia', 'Verdana')


def font_dir():
    """Where bundled fonts live. Overridable with MOEN_FONT_DIR."""
    explicit = getattr(settings, 'MOEN_FONT_DIR', None)
    if explicit:
        return str(explicit)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'static', 'Inventory', 'fonts')


def _parse(filename):
    """'Tahoma-BoldItalic.ttf' -> ('Tahoma', 'bold', 'italic'). None if not a font."""
    stem, ext = os.path.splitext(filename)
    if ext.lower() not in FONT_EXTENSIONS:
        return None

    weight, style = 'normal', 'normal'
    parts = stem.replace('_', '-').split('-')
    family = parts[0]

    suffix = ''.join(parts[1:]).lower()
    if 'bold' in suffix:
        weight = 'bold'
    if 'italic' in suffix or 'oblique' in suffix:
        style = 'italic'

    # CamelCase filenames such as TimesNewRoman.ttf -> "Times New Roman".
    if family and family[0].isupper() and any(c.isupper() for c in family[1:]):
        spaced, prev_lower = family[0], False
        for ch in family[1:]:
            if ch.isupper() and prev_lower:
                spaced += ' '
            spaced += ch
            prev_lower = ch.islower()
        family = spaced

    return family, weight, style


@lru_cache(maxsize=1)
def _scan():
    """{family: {(weight, style): abspath}} for everything on disk."""
    directory = font_dir()
    found = {}
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return found          # no fonts bundled — entirely normal

    for name in entries:
        parsed = _parse(name)
        if not parsed:
            continue
        family, weight, style = parsed
        path = os.path.abspath(os.path.join(directory, name))
        if os.path.isfile(path):
            found.setdefault(family, {})[(weight, style)] = path

    if found:
        logger.info("Bundled document fonts: %s", ', '.join(sorted(found)))
    return found


def clear_cache():
    """Forget the disk scan — call after adding a font without a restart."""
    _scan.cache_clear()


def available_families():
    """Families with at least a regular face, in KNOWN_FAMILIES order first.

    Only these are offered in the editor's font menu: a menu entry that cannot
    render is worse than no entry at all.
    """
    scanned = _scan()
    usable = [f for f, faces in scanned.items() if ('normal', 'normal') in faces]
    ordered = [f for f in KNOWN_FAMILIES if f in usable]
    ordered += sorted(f for f in usable if f not in KNOWN_FAMILIES)
    return ordered


def font_face_css():
    """@font-face rules for every bundled face, or '' when none are bundled.

    Emitted into the document template's <style>, so it applies identically to
    the on-screen preview and the WeasyPrint render.
    """
    rules = []
    for family, faces in sorted(_scan().items()):
        for (weight, style), path in sorted(faces.items()):
            # Absolute file:// URL — WeasyPrint resolves these; the browser
            # preview ignores cross-origin file URLs and falls back to the
            # stack, which is why the CSS keeps generic families after it.
            url = 'file://' + path.replace('\\', '/')
            rules.append(
                "@font-face { font-family: '%s'; src: url('%s'); "
                "font-weight: %s; font-style: %s; }" % (family, url, weight, style))
    return '\n  '.join(rules)
