#!/usr/bin/env python3
"""
Temporary tenant management script for creating new tenants.
Usage: python tenant_manager.py create <name> <schema> <host>
"""

import argparse
import re
import secrets
import string
import sys
from pathlib import Path

# Add the parent directory to the Python path so we can import from server package
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.database.multi_tenancy import (
    get_tenant_by_host,
    get_tenant_by_schema,
    tenant_create,
    tenant_delete,
)
from server.database.service import DatabaseService
from server.settings_tenant import set_tenant_setting


def generate_secure_api_key(length: int = 32) -> str:
    """Generate a secure API key."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def validate_tenant_data(name: str, schema: str, host: str) -> tuple[bool, str]:
    """Validate tenant data before creation."""

    # Validate name
    if not name or len(name.strip()) == 0:
        return False, 'Tenant name cannot be empty'

    if len(name) > 256:
        return False, 'Tenant name must be 256 characters or less'

    # Validate schema
    if not schema or len(schema.strip()) == 0:
        return False, 'Schema name cannot be empty'

    if len(schema) > 256:
        return False, 'Schema name must be 256 characters or less'

    # Schema should be lowercase and contain only alphanumeric characters and underscores
    if not re.match(r'^[a-z][a-z0-9_]*$', schema):
        return (
            False,
            'Schema name must start with a letter and contain only lowercase letters, numbers, and underscores',
        )

    # Validate host
    if not host or len(host.strip()) == 0:
        return False, 'Host cannot be empty'

    if len(host) > 256:
        return False, 'Host must be 256 characters or less'

    # Basic host validation (should be a valid domain or localhost)
    if not re.match(r'^[a-zA-Z0-9.-]+$', host) and host != 'localhost':
        return False, 'Host must be a valid domain name or localhost'

    return True, ''


def check_existing_tenant(schema: str, host: str) -> tuple[bool, str]:
    """Check if tenant already exists with the given schema or host."""

    # Check for existing schema
    existing_by_schema = get_tenant_by_schema(schema)
    if existing_by_schema:
        return False, f"Tenant with schema '{schema}' already exists"

    # Check for existing host
    existing_by_host = get_tenant_by_host(host)
    if existing_by_host:
        return False, f"Tenant with host '{host}' already exists"

    return True, ''


def create_tenant(name: str, schema: str, host: str) -> bool:
    """Create a new tenant."""

    print('Creating tenant:')
    print(f'  Name: {name}')
    print(f'  Schema: {schema}')
    print(f'  Host: {host}')
    print()

    # Validate input
    is_valid, error_msg = validate_tenant_data(name, schema, host)
    if not is_valid:
        print(f'❌ Validation error: {error_msg}')
        return False

    # Check for existing tenants
    is_unique, error_msg = check_existing_tenant(schema, host)
    if not is_unique:
        print(f'❌ Conflict error: {error_msg}')
        return False

    try:
        # Create the tenant
        tenant_create(name, schema, host)

        # Generate and store a secure API key for the new tenant
        api_key = generate_secure_api_key()
        set_tenant_setting(schema, 'API_KEY', api_key)

        print(f"✅ Tenant '{name}' created successfully!")
        print(f'   Schema: {schema}')
        print(f'   Host: {host}')
        print(f'   API Key: {api_key}')
        print()
        print('🔑 API Key Information:')
        print('   This API key provides full access to the tenant.')
        print('   Store it securely - it cannot be recovered if lost.')
        print('   Use this key to authenticate API requests for this tenant.')
        return True

    except Exception as e:
        print(f'❌ Error creating tenant: {str(e)}')
        return False


def delete_tenant(schema: str) -> bool:
    """Delete a tenant."""
    try:
        tenant_delete(schema)
        return True
    except Exception as e:
        print(f'❌ Error deleting tenant: {str(e)}')
        return False


def list_tenants() -> None:
    """List all tenants."""
    db_service = DatabaseService()
    tenants = db_service.list_tenants(include_inactive=True)

    if not tenants:
        print('No tenants found.')
        return

    print(f'Found {len(tenants)} tenant(s):')
    print()

    for tenant in tenants:
        status = '🟢 Active' if tenant.get('is_active') else '🔴 Inactive'
        print(f'  {tenant.get("name", "N/A")} ({status})')
        print(f'    Schema: {tenant.get("schema", "N/A")}')
        print(f'    Host: {tenant.get("host", "N/A")}')
        print(f'    ID: {tenant.get("id", "N/A")}')
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Temporary tenant management script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tenant_manager.py create "My Company" mycompany mycompany.lvh.me
  python tenant_manager.py create "Test Tenant" test_tenant test.lvh.me
  python tenant_manager.py list
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new tenant')
    create_parser.add_argument('name', help='Tenant name')
    create_parser.add_argument(
        'schema', help='Database schema name (lowercase, alphanumeric + underscores)'
    )
    create_parser.add_argument('host', help='Host domain for the tenant')

    # List command
    subparsers.add_parser('list', help='List all tenants')

    args = parser.parse_args()

    if args.command == 'create':
        success = create_tenant(args.name, args.schema, args.host)
        sys.exit(0 if success else 1)
    elif args.command == 'list':
        list_tenants()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
