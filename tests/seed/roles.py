"""Seed data for Roles."""

from fcontrol_api.models.security.resources import Roles

ROLES = [
    Roles(
        name='admin', description='Administrator role with full permissions'
    ),
    Roles(
        name='user', description='Standard user role with basic permissions'
    ),
    Roles(name='viewer', description='Viewer role with read-only permissions'),
]
