# Environment Configuration Setup

This document describes the centralized environment configuration system implemented for the project using the `environs` package.

## Overview

The project now uses a centralized environment configuration system that:
- Uses the `environs` package for robust environment variable handling
- Validates essential environment variables on startup
- Provides type conversion and validation
- Keeps AI provider configurations optional
- Centralizes all environment variable access

## Configuration Structure

### Core Configuration File: `server/config/environment.py`

The main configuration is handled by the `EnvironmentConfig` class which:

1. **Loads environment variables** from `.env` files if they exist
2. **Validates essential variables** and fails fast if missing
3. **Provides optional AI provider configurations**
4. **Sets up provider-specific environment variables**

### Essential Environment Variables

These variables are required and the application will fail to start if they're missing:

- `API_KEY`: The main API key for the application (must not be the default 'your_secret_api_key')

### Core Environment Variables

- `API_PROVIDER`: AI provider to use ('anthropic', 'bedrock', 'vertex') - defaults to 'anthropic'
- `DATABASE_URL`: Database connection string - defaults to 'sqlite:///server/server.db'
- `FASTAPI_SERVER_PORT`: Port for the FastAPI server - defaults to 8088
- `ENVIRONMENT`: Application environment - defaults to 'development'

### AI Provider-Specific Variables

#### Anthropic (default)
- `ANTHROPIC_API_KEY`: Required when using 'anthropic' provider

#### AWS Bedrock
- `AWS_ACCESS_KEY_ID`: Required when using 'bedrock' provider
- `AWS_SECRET_ACCESS_KEY`: Required when using 'bedrock' provider
- `AWS_REGION`: Required when using 'bedrock' provider
- `AWS_SESSION_TOKEN`: Optional session token for temporary credentials

#### Vertex AI
- `VERTEX_REGION`: Required when using 'vertex' provider
- `VERTEX_PROJECT_ID`: Required when using 'vertex' provider

### Optional Configuration Variables

- `SHOW_DOCS`: Show API documentation - defaults to false
- `HIDE_INTERNAL_API_ENDPOINTS_IN_DOC`: Hide internal endpoints in docs - defaults to false
- `API_SENTRY_DSN`: Sentry DSN for error tracking - optional
- `LOG_RETENTION_DAYS`: Days to keep logs - defaults to 7
- `VITE_PUBLIC_POSTHOG_KEY`: PostHog key for analytics - optional
- `VITE_PUBLIC_POSTHOG_HOST`: PostHog host - defaults to 'https://eu.i.posthog.com'
- `VITE_PUBLIC_DISABLE_TRACKING`: Disable analytics tracking - defaults to false

## Usage

### Importing Configuration

```python
from server.config import config

# Access configuration values
api_provider = config.API_PROVIDER
database_url = config.DATABASE_URL
api_key = config.API_KEY
```

### Validation

The configuration performs two types of validation:

1. **Essential Variables**: Validates that critical variables are set
2. **AI Provider Validation**: Validates that the selected AI provider has required credentials

```python
# These are called automatically in server startup
config.validate_essential_variables()
config.validate_ai_provider_settings()
config.setup_provider_environment()
```

## Files Updated

The following files were updated to use the centralized configuration:

1. **`server/config/environment.py`** - New centralized configuration
2. **`server/config/__init__.py`** - Package initialization
3. **`server/server.py`** - Main server startup and validation
4. **`server/core.py`** - Core API gateway functionality
5. **`server/database/service.py`** - Database service
6. **`server/utils/auth.py`** - Authentication utilities
7. **`server/utils/telemetry.py`** - Telemetry configuration
8. **`server/migrations/env.py`** - Alembic migration configuration
9. **`server/computer_use/sampling_loop.py`** - AI sampling loop AWS credentials

## Benefits

1. **Centralized Configuration**: All environment variables are managed in one place
2. **Type Safety**: Automatic type conversion and validation
3. **Fail Fast**: Essential variables are validated on startup
4. **Provider Flexibility**: AI provider configurations are optional and validated based on selection
5. **Clear Documentation**: All environment variables are documented in one place
6. **Consistent Access**: All modules use the same configuration interface

## Error Handling

The system provides clear error messages when:
- Essential variables are missing
- AI provider credentials are missing for the selected provider
- Environment variables have invalid values

Example error message:
```
Essential environment variables missing: API_KEY. Please set these variables before starting the application.
```

## Environment File Support

The configuration automatically loads from `.env` files if they exist in the server directory. This allows for easy local development configuration.

## Migration from Previous System

The previous system used `os.getenv()` calls scattered throughout the codebase. These have been replaced with centralized configuration access, providing better maintainability and validation.