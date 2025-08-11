"""
Utility functions for the Inventory application.
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
    A user is considered a schedule officer if they are in the 'Schedule Officer' group.
    """
    return user.groups.filter(name='Schedule Officer').exists() or user.is_superuser

def is_management(user):
    """
    Check if the user is in the management group.
    A user is considered management if they are in the 'Management' group.
    """
    return user.groups.filter(name='Management').exists() or user.is_superuser
