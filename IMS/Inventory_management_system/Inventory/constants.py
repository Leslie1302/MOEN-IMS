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
