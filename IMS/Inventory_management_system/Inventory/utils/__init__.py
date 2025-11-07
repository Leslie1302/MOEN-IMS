"""
Utils package for Inventory application.
Provides utility functions for role checking and permissions.
"""

def is_storekeeper(user):
    """
    Check if the user is a storekeeper.
    A user is considered a storekeeper if they are in the 'Storekeeper' group.
    """
    return user.groups.filter(name='Storekeeper').exists() or user.is_superuser

def is_superuser(user):
    """
    Check if the user is a superuser.
    This is a simple wrapper around user.is_superuser for consistency.
    """
    return user.is_superuser

def is_schedule_officer(user):
    """
    Check if the user is a schedule officer.
    A user is considered a schedule officer if they are in the 'Schedule Officers' group.
    """
    return user.groups.filter(name='Schedule Officers').exists() or user.is_superuser

def is_management(user):
    """
    Check if the user is in the management group.
    A user is considered management if they are in the 'Management' group.
    """
    return user.groups.filter(name='Management').exists() or user.is_superuser

def is_consultant(user):
    """
    Check if the user is a consultant.
    A user is considered a consultant if they are in the 'Consultant' group.
    """
    return user.groups.filter(name='Consultant').exists() or user.is_superuser

def is_transport_officer(user):
    """
    Check if the user is a transport officer.
    A user is considered a transport officer if they are in the 'Transport Officer' group.
    """
    return user.groups.filter(name='Transport Officer').exists() or user.is_superuser

__all__ = [
    'is_storekeeper',
    'is_superuser',
    'is_schedule_officer',
    'is_management',
    'is_consultant',
    'is_transport_officer'
]
