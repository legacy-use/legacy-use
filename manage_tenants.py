#!/usr/bin/env python3
"""
Tenant management CLI script for the multi-tenant API Gateway.

This script provides commands to create, list, and manage tenants.
"""

import argparse
import sys
from uuid import UUID

from server.database import db
from server.utils.tenant import initialize_shared_schema
from server.database.models import TenantModel


def create_tenant(name: str, subdomain: str):
    """Create a new tenant."""
    try:
        # Check if subdomain already exists
        existing_tenants = db.list_tenants(include_inactive=True)
        for existing in existing_tenants:
            if existing['subdomain'] == subdomain:
                print(f"❌ Error: Subdomain '{subdomain}' already exists")
                return False
        
        # Create tenant
        tenant = db.create_tenant({
            'name': name,
            'subdomain': subdomain
        })
        
        print(f"✅ Successfully created tenant:")
        print(f"   Name: {tenant['name']}")
        print(f"   Subdomain: {tenant['subdomain']}")
        print(f"   Schema: {tenant['schema_name']}")
        print(f"   API Key: {tenant['api_key']}")
        print(f"   Tenant ID: {tenant['id']}")
        print()
        print("⚠️  IMPORTANT: Save the API key securely - it won't be shown again!")
        
        return True
    except Exception as e:
        print(f"❌ Error creating tenant: {e}")
        return False


def list_tenants(include_inactive: bool = False):
    """List all tenants."""
    try:
        tenants = db.list_tenants(include_inactive=include_inactive)
        
        if not tenants:
            print("No tenants found.")
            return
        
        print(f"Found {len(tenants)} tenant(s):")
        print()
        
        for tenant in tenants:
            status_icon = "✅" if tenant['status'] == 'active' else "❌"
            print(f"{status_icon} {tenant['name']}")
            print(f"   ID: {tenant['id']}")
            print(f"   Subdomain: {tenant['subdomain']}")
            print(f"   Schema: {tenant['schema_name']}")
            print(f"   Status: {tenant['status']}")
            print(f"   Created: {tenant['created_at']}")
            print()
            
    except Exception as e:
        print(f"❌ Error listing tenants: {e}")


def regenerate_api_key(tenant_id: str):
    """Regenerate API key for a tenant."""
    try:
        tenant_uuid = UUID(tenant_id)
        tenant = db.regenerate_tenant_api_key(tenant_uuid)
        
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return False
        
        print(f"✅ Successfully regenerated API key for tenant '{tenant['name']}':")
        print(f"   New API Key: {tenant['api_key']}")
        print()
        print("⚠️  IMPORTANT: Save the new API key securely - it won't be shown again!")
        print("⚠️  The old API key is now invalid!")
        
        return True
    except ValueError:
        print(f"❌ Invalid tenant ID format: {tenant_id}")
        return False
    except Exception as e:
        print(f"❌ Error regenerating API key: {e}")
        return False


def deactivate_tenant(tenant_id: str):
    """Deactivate a tenant."""
    try:
        tenant_uuid = UUID(tenant_id)
        tenant = db.update_tenant(tenant_uuid, {'status': 'inactive'})
        
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return False
        
        print(f"✅ Successfully deactivated tenant '{tenant['name']}'")
        return True
    except ValueError:
        print(f"❌ Invalid tenant ID format: {tenant_id}")
        return False
    except Exception as e:
        print(f"❌ Error deactivating tenant: {e}")
        return False


def activate_tenant(tenant_id: str):
    """Activate a tenant."""
    try:
        tenant_uuid = UUID(tenant_id)
        tenant = db.update_tenant(tenant_uuid, {'status': 'active'})
        
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return False
        
        print(f"✅ Successfully activated tenant '{tenant['name']}'")
        return True
    except ValueError:
        print(f"❌ Invalid tenant ID format: {tenant_id}")
        return False
    except Exception as e:
        print(f"❌ Error activating tenant: {e}")
        return False


def init_database():
    """Initialize the shared database schema."""
    try:
        initialize_shared_schema()
        print("✅ Successfully initialized shared database schema")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Manage tenants for the multi-tenant API Gateway"
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create tenant command
    create_parser = subparsers.add_parser('create', help='Create a new tenant')
    create_parser.add_argument('name', help='Tenant name')
    create_parser.add_argument('subdomain', help='Tenant subdomain')
    
    # List tenants command
    list_parser = subparsers.add_parser('list', help='List all tenants')
    list_parser.add_argument(
        '--include-inactive', 
        action='store_true', 
        help='Include inactive tenants'
    )
    
    # Regenerate API key command
    regen_parser = subparsers.add_parser('regenerate-key', help='Regenerate API key for a tenant')
    regen_parser.add_argument('tenant_id', help='Tenant ID (UUID)')
    
    # Deactivate tenant command
    deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate a tenant')
    deactivate_parser.add_argument('tenant_id', help='Tenant ID (UUID)')
    
    # Activate tenant command
    activate_parser = subparsers.add_parser('activate', help='Activate a tenant')
    activate_parser.add_argument('tenant_id', help='Tenant ID (UUID)')
    
    # Initialize database command
    init_parser = subparsers.add_parser('init-db', help='Initialize shared database schema')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute the appropriate command
    success = True
    
    if args.command == 'create':
        success = create_tenant(args.name, args.subdomain)
    elif args.command == 'list':
        list_tenants(args.include_inactive)
    elif args.command == 'regenerate-key':
        success = regenerate_api_key(args.tenant_id)
    elif args.command == 'deactivate':
        success = deactivate_tenant(args.tenant_id)
    elif args.command == 'activate':
        success = activate_tenant(args.tenant_id)
    elif args.command == 'init-db':
        success = init_database()
    
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()