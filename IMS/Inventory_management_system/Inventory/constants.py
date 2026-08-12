"""
Project-wide constants and small lookup helpers.

This module exists so that string identifiers like project type codes are
defined in exactly one place. Anywhere we used to have hardcoded strings
("SHEP", "Cost-sharing", etc.) scattered across views and templates, we now
import from here -- keeping the canonical list in lockstep with the
ProjectType database rows.
"""

# Canonical project type codes. These match ProjectType.code values seeded
# in migration Inventory.0032_seed_project_types_and_people.
PROJECT_TYPE_SHEP = 'shep'
PROJECT_TYPE_COST_SHARING = 'cost_sharing'
PROJECT_TYPE_STREETLIGHTS = 'streetlights'

# Deprecated alias: kept so the brief 'poles' rename (0055) doesn't break
# any straggler imports during rollback. New code should use
# PROJECT_TYPE_STREETLIGHTS.
PROJECT_TYPE_POLES = PROJECT_TYPE_STREETLIGHTS

CANONICAL_PROJECT_TYPE_CODES = (
    PROJECT_TYPE_SHEP,
    PROJECT_TYPE_COST_SHARING,
    PROJECT_TYPE_STREETLIGHTS,
)

# Legacy project type names from the old Project.project_type CharField.
# Kept here so the data migration that converts the CharField to a FK can
# map historical values to the new ProjectType rows. After Phase A these
# are not used by any new code.
LEGACY_PROJECT_TYPE_MAP = {
    'SHEP': PROJECT_TYPE_SHEP,
    'Turnkey': 'turnkey',                             # archived (active=False)
    'China Water': 'china_water',                     # archived
    'Other Electrification': 'other_electrification', # archived
    # MaterialOrder used different short codes; map them too:
    'COST': PROJECT_TYPE_COST_SHARING,
    'SPEC': 'special_other',                          # archived
    'STREET': PROJECT_TYPE_STREETLIGHTS,
    'POLES': PROJECT_TYPE_STREETLIGHTS,                # legacy short code from the brief 0055 rename
    'Cost-sharing': PROJECT_TYPE_COST_SHARING,
}

# Consignee role values mirror ProjectType.CONSIGNEE_ROLE_CHOICES.
CONSIGNEE_ROLE_CONSULTANT = 'consultant'
CONSIGNEE_ROLE_MP = 'mp'
CONSIGNEE_ROLE_OTHER = 'other'


def get_project_type(code):
    """
    Convenience accessor. Returns the ProjectType instance for the given
    code, or None if it doesn't exist. Imported lazily so this module can
    be imported during early Django setup before app loading completes.
    """
    from Inventory.models import ProjectType
    try:
        return ProjectType.objects.get(code=code)
    except ProjectType.DoesNotExist:
        return None


def active_project_types():
    """
    Returns the queryset of project types that should appear in user-facing
    dropdowns. Inactive (archived) types remain queryable but are hidden
    from new requests.
    """
    from Inventory.models import ProjectType
    return ProjectType.objects.filter(active=True).order_by('sort_order', 'name')


# Phase C: maps ProjectType.code (lowercase) to the legacy
# MaterialOrder.project_type CharField value. Used by the two-step request
# flow to write to the existing CharField until a future phase migrates
# MaterialOrder.project_type to a proper FK.
PROJECT_TYPE_TO_CHARFIELD = {
    PROJECT_TYPE_SHEP:         'SHEP',
    PROJECT_TYPE_COST_SHARING: 'COST',
    PROJECT_TYPE_STREETLIGHTS: 'STREET',
    'special_other':           'SPEC',
    'turnkey':                 'SPEC',
    'china_water':             'SPEC',
    'other_electrification':   'SPEC',
}


def project_type_to_charfield(project_type):
    """
    Translate a ProjectType instance (or code string) into the
    MaterialOrder.project_type CharField value. Defaults to 'SHEP' if the
    project type is unknown, which matches the model's default.
    """
    code = project_type.code if hasattr(project_type, 'code') else project_type
    return PROJECT_TYPE_TO_CHARFIELD.get(code, 'SHEP')


# ── One canonical project-type comparison ────────────────────────────────────
# project_type is stored in two value-spaces across the schema:
#   MaterialOrder/ReleaseLetter → short codes  ('SHEP', 'STREET', 'COST', 'SPEC')
#   BillOfQuantity              → display names ('SHEP', 'Streetlights', 'Cost Sharing')
# plus the ProjectType.code slugs ('shep', 'streetlights', 'cost_sharing').
# normalize_project_type() collapses ALL of them to the short code so any
# project-aware check compares like with like. Alphanumeric-only key so spacing
# and punctuation ('Cost Sharing' vs 'cost_sharing') never matter.
_PROJECT_TYPE_ALIASES = {
    'shep': 'SHEP',
    'street': 'STREET', 'streetlight': 'STREET', 'streetlights': 'STREET', 'poles': 'STREET',
    'cost': 'COST', 'costsharing': 'COST', 'costshare': 'COST',
    'spec': 'SPEC', 'special': 'SPEC', 'specialother': 'SPEC',
    'turnkey': 'SPEC', 'chinawater': 'SPEC', 'otherelectrification': 'SPEC',
}

# Programmes that are NOT scoped by a pre-loaded Bill of Quantity — the release
# order itself is the authorisation. SHEP (and anything unknown) is conventional.
NONCONVENTIONAL_PROJECT_TYPES = {'STREET', 'COST'}


def normalize_project_type(value):
    """Any spelling of a project type → its short code ('STREET'), or '' if unknown."""
    if not value:
        return ''
    key = ''.join(ch for ch in str(value).lower() if ch.isalnum())
    return _PROJECT_TYPE_ALIASES.get(key, '')


def is_nonconventional(value):
    """True for Streetlights / Cost-sharing (no pre-established BoQ scope)."""
    return normalize_project_type(value) in NONCONVENTIONAL_PROJECT_TYPES
