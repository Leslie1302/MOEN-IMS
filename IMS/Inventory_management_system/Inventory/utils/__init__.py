"""
Utils package for Inventory application.
Provides utility functions for role checking and permissions.

IMPORTANT: All role group names are defined as constants in the Roles class below.
When adding new role checks or referencing group names, always use these constants
to prevent drift between singular/plural forms.
"""


class Roles:
    """
    Canonical role group names — single source of truth.

    These MUST match the actual Group names stored in the database.
    If you rename a group in Django Admin, update the constant here.

    NOTE: Some modules previously used singular forms ('Store Officer',
    'Schedule Officer') while others used plural ('Store Officers',
    'Schedule Officers'). The values below reflect the names most
    commonly used in the active view layer. Verify they match your
    database groups.
    """
    STORE_OFFICER = 'Store Officers'
    SCHEDULE_OFFICER = 'Schedule Officers'
    MANAGEMENT = 'Management'
    CONSULTANT = 'Consultant'
    CONSULTANTS = 'Consultants'        # Plural form used in some views
    TRANSPORT_OFFICER = 'Transport Officer'
    STORES_MANAGEMENT = 'Stores Management'
    STORE_OPERATION_ALIASES = (
        'Store Officer',
        'Store Officers',
        'Storekeeper',
        'Storekeepers',
        'Stores Officer',
        'Stores Officers',
    )


def is_store_officer(user):
    """
    Check if the user is a store officer.
    A user is considered a store officer if they are in any store-operations
    group variant (singular/plural legacy names are both accepted).
    """
    return user.is_superuser or user.groups.filter(name__in=Roles.STORE_OPERATION_ALIASES).exists()


def is_store_operations_user(user):
    """
    Check if the user should see store-operations pages.
    Alias helper for navbar and read-only reconciliation views.
    """
    return is_store_officer(user)


def is_superuser(user):
    """
    Check if the user is a superuser.
    This is a simple wrapper around user.is_superuser for consistency.
    """
    return user.is_superuser


def is_schedule_officer(user):
    """
    Check if the user is a schedule officer.
    A user is considered a schedule officer if they are in the Schedule Officers group.
    """
    return user.groups.filter(name=Roles.SCHEDULE_OFFICER).exists() or user.is_superuser


def is_management(user):
    """
    Check if the user is in the management group.
    A user is considered management if they are in the 'Management' group.
    """
    return user.groups.filter(name=Roles.MANAGEMENT).exists() or user.is_superuser


def is_consultant(user):
    """
    Check if the user is a consultant.
    Accepts both the canonical 'Consultants' group and the legacy singular.
    """
    return user.groups.filter(
        name__in=(Roles.CONSULTANT, Roles.CONSULTANTS)
    ).exists() or user.is_superuser


def is_transport_officer(user):
    """
    Check if the user is a transport officer.
    A user is considered a transport officer if they are in the 'Transport Officer' group.
    """
    return user.groups.filter(name=Roles.TRANSPORT_OFFICER).exists() or user.is_superuser


__all__ = [
    'Roles',
    'is_store_officer',
    'is_store_operations_user',
    'is_superuser',
    'is_schedule_officer',
    'is_management',
    'is_consultant',
    'is_transport_officer',
]
