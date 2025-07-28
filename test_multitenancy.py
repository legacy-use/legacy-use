#!/usr/bin/env python3
"""
Test script to demonstrate multi-tenant functionality.
This script shows how the multi-tenant system works without requiring a full database setup.
"""

import hashlib
import secrets
import sys
from typing import Optional


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str, salt: str = None) -> tuple[str, str]:
    """Hash an API key with salt for secure storage."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Use PBKDF2 for secure hashing
    key_hash = hashlib.pbkdf2_hmac('sha256', api_key.encode(), salt.encode(), 100000)
    return key_hash.hex(), salt


def verify_api_key(api_key: str, stored_hash: str, salt: str) -> bool:
    """Verify an API key against stored hash."""
    key_hash, _ = hash_api_key(api_key, salt)
    return secrets.compare_digest(key_hash, stored_hash)


def generate_schema_name(subdomain: str) -> str:
    """Generate a schema name from subdomain."""
    return f"tenant_{subdomain.lower().replace('-', '_')}"


class MockTenant:
    """Mock tenant class for demonstration."""
    
    def __init__(self, name: str, subdomain: str):
        self.id = secrets.token_hex(16)
        self.name = name
        self.subdomain = subdomain
        self.schema_name = generate_schema_name(subdomain)
        self.status = 'active'
        
        # Generate secure API key
        self.api_key = generate_api_key()
        self.api_key_hash, self.api_key_salt = hash_api_key(self.api_key)
    
    def verify_key(self, api_key: str) -> bool:
        """Verify if the provided API key matches this tenant."""
        return verify_api_key(api_key, self.api_key_hash, self.api_key_salt)
    
    def to_dict(self):
        """Convert to dictionary (excluding sensitive data)."""
        return {
            'id': self.id,
            'name': self.name,
            'subdomain': self.subdomain,
            'schema_name': self.schema_name,
            'status': self.status
        }


def demonstrate_multitenancy():
    """Demonstrate multi-tenant functionality."""
    
    print("🏢 Multi-Tenant FastAPI Implementation Demo")
    print("=" * 50)
    print()
    
    # Create some test tenants
    tenants = [
        MockTenant("Acme Corporation", "acme"),
        MockTenant("TechStart Inc", "techstart"),
        MockTenant("Global Solutions", "global-solutions")
    ]
    
    print("📋 Created Tenants:")
    for tenant in tenants:
        print(f"  • {tenant.name}")
        print(f"    Subdomain: {tenant.subdomain}")
        print(f"    Schema: {tenant.schema_name}")
        print(f"    API Key: {tenant.api_key[:16]}...{tenant.api_key[-8:]}")
        print(f"    Tenant ID: {tenant.id}")
        print()
    
    print("🔐 Security Features Demonstration:")
    print()
    
    # Demonstrate secure API key hashing
    test_tenant = tenants[0]
    print(f"1. API Key Hashing for '{test_tenant.name}':")
    print(f"   Original API Key: {test_tenant.api_key}")
    print(f"   Hashed (stored):  {test_tenant.api_key_hash[:32]}...")
    print(f"   Salt:             {test_tenant.api_key_salt}")
    print()
    
    # Demonstrate API key verification
    print("2. API Key Verification:")
    correct_key = test_tenant.api_key
    wrong_key = generate_api_key()
    
    print(f"   ✅ Correct key verification: {test_tenant.verify_key(correct_key)}")
    print(f"   ❌ Wrong key verification:   {test_tenant.verify_key(wrong_key)}")
    print()
    
    # Demonstrate tenant isolation
    print("3. Tenant Isolation:")
    for tenant in tenants:
        print(f"   Tenant: {tenant.name}")
        print(f"   └── Database Schema: {tenant.schema_name}")
        print(f"       ├── targets table")
        print(f"       ├── sessions table")
        print(f"       ├── jobs table")
        print(f"       └── job_logs table")
    print()
    
    # Demonstrate API request routing
    print("4. API Request Routing Simulation:")
    print()
    
    def simulate_api_request(api_key: str, endpoint: str):
        """Simulate an API request with tenant resolution."""
        # Find tenant by API key
        authenticated_tenant = None
        for tenant in tenants:
            if tenant.verify_key(api_key):
                authenticated_tenant = tenant
                break
        
        if not authenticated_tenant:
            return f"❌ 401 Unauthorized - Invalid API key"
        
        return f"✅ 200 OK - {endpoint} (Tenant: {authenticated_tenant.name}, Schema: {authenticated_tenant.schema_name})"
    
    # Test API requests
    test_cases = [
        (tenants[0].api_key, "GET /targets"),
        (tenants[1].api_key, "POST /sessions"),
        (tenants[2].api_key, "GET /jobs"),
        ("invalid-key-12345", "GET /targets"),
    ]
    
    for api_key, endpoint in test_cases:
        result = simulate_api_request(api_key, endpoint)
        print(f"   Request: {endpoint}")
        print(f"   API Key: {api_key[:16]}...{api_key[-8:] if len(api_key) > 24 else api_key}")
        print(f"   Result:  {result}")
        print()
    
    print("📊 Multi-Tenant Benefits:")
    print("  ✅ Strong data isolation between tenants")
    print("  ✅ Secure API key storage with PBKDF2 hashing")
    print("  ✅ Automatic schema-based routing")
    print("  ✅ No risk of cross-tenant data access")
    print("  ✅ Scalable architecture")
    print("  ✅ Easy tenant management")
    print()
    
    print("🚀 Next Steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Initialize database: python manage_tenants.py init-db")
    print("  3. Create your first tenant: python manage_tenants.py create 'My Company' my-company")
    print("  4. Start the server: python -m server.server")
    print("  5. Test with: curl -H 'X-API-Key: YOUR_KEY' http://localhost:8000/tenant-info")


if __name__ == '__main__':
    demonstrate_multitenancy()