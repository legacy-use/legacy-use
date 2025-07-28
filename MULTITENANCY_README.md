# Multi-Tenant FastAPI Implementation

This document describes the multi-tenant architecture implemented for the AI API Gateway, providing secure data isolation and API key management for multiple tenants.

## Overview

The implementation uses a **Single Database, Multiple Schemas** approach, which provides:

- ✅ Strong data isolation between tenants
- ✅ Secure API key storage with PBKDF2 hashing
- ✅ Automatic schema management
- ✅ Tenant-aware database operations
- ✅ Easy tenant management via CLI and API
- ✅ Backward compatibility with existing code

## Architecture

### Database Structure

```
Database
├── shared (schema)
│   └── tenants (table) - Tenant metadata and API keys
├── tenant_company1 (schema)
│   ├── targets (table)
│   ├── sessions (table)
│   ├── jobs (table)
│   └── ... (all tenant-specific tables)
└── tenant_company2 (schema)
    ├── targets (table)
    ├── sessions (table)
    ├── jobs (table)
    └── ... (all tenant-specific tables)
```

### Key Components

1. **Tenant Models** (`server/models/tenant.py`)
   - Pydantic models for tenant operations
   - Secure API key handling

2. **Database Models** (`server/database/models.py`)
   - SQLAlchemy models with schema support
   - Tenant-specific and shared table definitions

3. **Tenant Utilities** (`server/utils/tenant.py`)
   - Schema management functions
   - API key generation and verification
   - Database session management

4. **Authentication** (`server/utils/auth.py`)
   - Multi-tenant API key authentication
   - Tenant resolution from API keys

5. **Database Service** (`server/database/service.py`)
   - Tenant-aware database operations
   - Automatic schema routing

## Security Features

### API Key Security

- **PBKDF2 Hashing**: API keys are hashed using PBKDF2 with 100,000 iterations
- **Salt Generation**: Each API key uses a unique random salt
- **Constant-time Comparison**: Uses `secrets.compare_digest()` to prevent timing attacks
- **One-time Display**: API keys are only shown once during creation/regeneration

### Data Isolation

- **Schema Separation**: Each tenant gets their own database schema
- **Automatic Routing**: Middleware automatically routes requests to the correct tenant schema
- **No Cross-tenant Access**: Impossible to accidentally access another tenant's data

## Getting Started

### 1. Initialize the Database

```bash
# Initialize shared schema and tables
python manage_tenants.py init-db
```

### 2. Create Your First Tenant

```bash
# Create a tenant
python manage_tenants.py create "Company A" company-a

# Output:
# ✅ Successfully created tenant:
#    Name: Company A
#    Subdomain: company-a
#    Schema: tenant_company_a
#    API Key: abc123...xyz789
#    Tenant ID: 550e8400-e29b-41d4-a716-446655440000
# 
# ⚠️  IMPORTANT: Save the API key securely - it won't be shown again!
```

### 3. Test the API

```bash
# Use the tenant's API key to make requests
curl -H "X-API-Key: abc123...xyz789" http://localhost:8000/tenant-info

# Response:
# {
#   "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
#   "name": "Company A",
#   "subdomain": "company-a",
#   "status": "active"
# }
```

## Tenant Management

### CLI Commands

```bash
# List all tenants
python manage_tenants.py list

# List including inactive tenants
python manage_tenants.py list --include-inactive

# Regenerate API key for a tenant
python manage_tenants.py regenerate-key <tenant-id>

# Deactivate a tenant
python manage_tenants.py deactivate <tenant-id>

# Activate a tenant
python manage_tenants.py activate <tenant-id>
```

### API Endpoints

#### Tenant Management (Admin Only)

```http
POST /tenants
GET /tenants
GET /tenants/{tenant_id}
PUT /tenants/{tenant_id}
DELETE /tenants/{tenant_id}
POST /tenants/{tenant_id}/regenerate-api-key
```

#### Tenant Information

```http
GET /tenant-info - Get current tenant info
GET /tenants/current - Get current tenant details
```

## API Usage

### Authentication

All API requests (except tenant management) require the tenant's API key:

```http
X-API-Key: your-tenant-api-key
```

### Example Requests

```bash
# Get tenant information
curl -H "X-API-Key: your-api-key" \
     http://localhost:8000/tenant-info

# List targets (tenant-specific)
curl -H "X-API-Key: your-api-key" \
     http://localhost:8000/targets

# Create a new target (tenant-specific)
curl -X POST \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"name": "My Target", "type": "rdp", "host": "example.com", "password": "secret"}' \
     http://localhost:8000/targets
```

## Migration from Single-Tenant

If you're migrating from a single-tenant setup:

1. **Backup your database** - Important!

2. **Run the migration**:
   ```bash
   python manage_tenants.py init-db
   ```

3. **Create a tenant for existing data**:
   ```bash
   python manage_tenants.py create "Default Tenant" default
   ```

4. **Update your API calls** to use the new tenant API key instead of the old global API key.

## Development

### Adding New Models

When adding new models that should be tenant-specific:

```python
from server.database.models import TenantBase

class MyNewModel(TenantBase):
    __tablename__ = 'my_new_table'
    
    # Your model fields here
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    # ...
```

### Adding Shared Models

For models that should be shared across all tenants:

```python
from server.database.models import Base

class MySharedModel(Base):
    __tablename__ = 'my_shared_table'
    
    # Your model fields here
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    # ...
    
    # Important: Specify shared schema
    __table_args__ = {'schema': 'shared'}
```

### Accessing Tenant Context

In your route handlers, you can access tenant information:

```python
from fastapi import Depends, Request
from server.database.models import TenantModel
from server.server import get_request_tenant, get_tenant_db

@router.get("/my-endpoint")
async def my_endpoint(
    tenant: TenantModel = Depends(get_request_tenant),
    db = Depends(get_tenant_db)
):
    # tenant contains current tenant info
    # db is automatically configured for the tenant's schema
    
    # Your logic here
    pass
```

## Configuration

### Environment Variables

The multi-tenant system uses the same database configuration as the single-tenant version:

```env
DATABASE_URL=sqlite:///server/server.db
# or
DATABASE_URL=postgresql://user:password@localhost/dbname
```

### Settings

No additional settings are required. The system automatically:
- Initializes shared schema on startup
- Creates tenant schemas as needed
- Routes database operations to the correct schema

## Monitoring and Maintenance

### Log Pruning

The system automatically prunes old logs for all tenants:
- Runs daily at midnight
- Configurable retention period via `LOG_RETENTION_DAYS`
- Processes all active tenants

### Database Maintenance

```bash
# Check tenant schemas
python -c "
from server.database import db
tenants = db.list_tenants()
for tenant in tenants:
    print(f'Tenant: {tenant[\"name\"]} -> Schema: {tenant[\"schema_name\"]}')
"

# Verify tenant isolation
python -c "
from server.utils.tenant import get_tenant_db_session
with get_tenant_db_session('tenant_company1') as session:
    # This session can only access tenant_company1 schema
    pass
"
```

## Security Considerations

1. **API Key Storage**: Never store API keys in plain text
2. **Tenant Management**: Restrict tenant management endpoints to admin users
3. **Schema Access**: The system prevents cross-tenant data access
4. **Key Rotation**: Regularly rotate API keys using the regenerate function
5. **Monitoring**: Monitor for unusual cross-tenant access attempts

## Troubleshooting

### Common Issues

1. **"Tenant not found" errors**
   - Verify the API key is correct
   - Check if the tenant is active
   - Ensure the tenant exists in the database

2. **Schema not found errors**
   - The tenant's schema may not have been created
   - Try recreating the tenant or manually create the schema

3. **Migration issues**
   - Ensure you have proper database permissions
   - Check that the shared schema was created successfully

### Debug Commands

```bash
# Check if shared schema exists
python -c "
from server.utils.tenant import get_tenant_db_session
with get_tenant_db_session() as session:
    result = session.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"tenants\"')
    print('Tenants table exists:', result.fetchone() is not None)
"

# List all schemas (PostgreSQL)
python -c "
from server.utils.tenant import get_tenant_db_session
with get_tenant_db_session() as session:
    result = session.execute('SELECT schema_name FROM information_schema.schemata')
    print('Schemas:', [row[0] for row in result.fetchall()])
"
```

## Performance Considerations

- **Connection Pooling**: Each tenant uses the same connection pool
- **Schema Translation**: Minimal overhead for schema mapping
- **Index Strategy**: Each tenant has their own indexes for optimal performance
- **Query Isolation**: Queries are automatically scoped to the tenant's schema

## Future Enhancements

Potential improvements for the multi-tenant system:

1. **Tenant-specific Settings**: Custom configuration per tenant
2. **Resource Limits**: Per-tenant quotas and rate limiting
3. **Analytics**: Tenant usage metrics and reporting
4. **Backup/Restore**: Tenant-specific backup and restore capabilities
5. **Migration Tools**: Automated tenant data migration utilities

---

For more information or support, please refer to the main project documentation or open an issue in the repository.