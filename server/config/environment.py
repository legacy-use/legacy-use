"""
Environment configuration using environs package.
Provides centralized environment variable handling with validation and type conversion.
"""

import os
from pathlib import Path
from typing import Optional

from environs import Env

# Initialize environs
env = Env()

# Load environment variables from .env file if it exists
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    env.read_env(str(env_path))


class EnvironmentConfig:
    """Centralized environment configuration with validation."""
    
    def __init__(self):
        # Core API settings (required)
        self.API_KEY: str = env.str('API_KEY', 'your_secret_api_key')
        self.API_PROVIDER: str = env.str('API_PROVIDER', 'anthropic')
        
        # Server settings
        self.FASTAPI_SERVER_PORT: int = env.int('FASTAPI_SERVER_PORT', 8088)
        self.ENVIRONMENT: str = env.str('ENVIRONMENT', 'development')
        
        # Database settings (required)
        self.DATABASE_URL: str = env.str('DATABASE_URL', 'sqlite:///server/server.db')
        
        # Authentication settings
        self.SHOW_DOCS: bool = env.bool('SHOW_DOCS', False)
        self.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC: bool = env.bool(
            'HIDE_INTERNAL_API_ENDPOINTS_IN_DOC', False
        )
        
        # Telemetry settings
        self.VITE_PUBLIC_POSTHOG_KEY: Optional[str] = env.str(
            'VITE_PUBLIC_POSTHOG_KEY', None
        )
        self.VITE_PUBLIC_POSTHOG_HOST: str = env.str(
            'VITE_PUBLIC_POSTHOG_HOST', 'https://eu.i.posthog.com'
        )
        self.VITE_PUBLIC_DISABLE_TRACKING: bool = env.bool(
            'VITE_PUBLIC_DISABLE_TRACKING', False
        )
        
        # Monitoring settings
        self.API_SENTRY_DSN: Optional[str] = env.str('API_SENTRY_DSN', None)
        self.LOG_RETENTION_DAYS: int = env.int('LOG_RETENTION_DAYS', 7)
        
        # AI Provider-specific settings (optional)
        self._init_ai_provider_settings()
    
    def _init_ai_provider_settings(self):
        """Initialize AI provider-specific settings."""
        # Anthropic settings (optional)
        self.ANTHROPIC_API_KEY: Optional[str] = env.str('ANTHROPIC_API_KEY', None)
        
        # AWS/Bedrock settings (optional)
        self.AWS_ACCESS_KEY_ID: Optional[str] = env.str('AWS_ACCESS_KEY_ID', None)
        self.AWS_SECRET_ACCESS_KEY: Optional[str] = env.str('AWS_SECRET_ACCESS_KEY', None)
        self.AWS_REGION: Optional[str] = env.str('AWS_REGION', None)
        self.AWS_SESSION_TOKEN: Optional[str] = env.str('AWS_SESSION_TOKEN', None)
        
        # Vertex AI settings (optional)
        self.VERTEX_REGION: Optional[str] = env.str('VERTEX_REGION', None)
        self.VERTEX_PROJECT_ID: Optional[str] = env.str('VERTEX_PROJECT_ID', None)
    
    def validate_essential_variables(self):
        """Validate that all essential variables are present."""
        missing_vars = []
        
        # Check for essential database configuration
        if not self.DATABASE_URL or self.DATABASE_URL == 'sqlite:///server/server.db':
            # SQLite default is acceptable for development
            pass
        
        # Check for essential API key
        if not self.API_KEY or self.API_KEY == 'your_secret_api_key':
            missing_vars.append('API_KEY')
        
        if missing_vars:
            raise ValueError(
                f"Essential environment variables missing: {', '.join(missing_vars)}. "
                f"Please set these variables before starting the application."
            )
    
    def validate_ai_provider_settings(self):
        """Validate AI provider-specific settings based on the selected provider."""
        if self.API_PROVIDER == 'anthropic':
            if not self.ANTHROPIC_API_KEY:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required when using 'anthropic' provider"
                )
        elif self.API_PROVIDER == 'bedrock':
            missing_aws_vars = []
            if not self.AWS_ACCESS_KEY_ID:
                missing_aws_vars.append('AWS_ACCESS_KEY_ID')
            if not self.AWS_SECRET_ACCESS_KEY:
                missing_aws_vars.append('AWS_SECRET_ACCESS_KEY')
            if not self.AWS_REGION:
                missing_aws_vars.append('AWS_REGION')
            
            if missing_aws_vars:
                raise ValueError(
                    f"AWS credentials missing for bedrock provider: {', '.join(missing_aws_vars)}. "
                    f"Please set these variables when using the bedrock provider."
                )
        elif self.API_PROVIDER == 'vertex':
            missing_vertex_vars = []
            if not self.VERTEX_REGION:
                missing_vertex_vars.append('VERTEX_REGION')
            if not self.VERTEX_PROJECT_ID:
                missing_vertex_vars.append('VERTEX_PROJECT_ID')
            
            if missing_vertex_vars:
                raise ValueError(
                    f"Vertex AI credentials missing for vertex provider: {', '.join(missing_vertex_vars)}. "
                    f"Please set these variables when using the vertex provider."
                )
    
    def setup_provider_environment(self):
        """Set up environment variables for the selected AI provider."""
        if self.API_PROVIDER == 'bedrock' and all([
            self.AWS_ACCESS_KEY_ID,
            self.AWS_SECRET_ACCESS_KEY,
            self.AWS_REGION
        ]):
            # Type checks already done by the all() condition above
            os.environ['AWS_ACCESS_KEY_ID'] = str(self.AWS_ACCESS_KEY_ID)
            os.environ['AWS_SECRET_ACCESS_KEY'] = str(self.AWS_SECRET_ACCESS_KEY)
            os.environ['AWS_REGION'] = str(self.AWS_REGION)
            if self.AWS_SESSION_TOKEN:
                os.environ['AWS_SESSION_TOKEN'] = str(self.AWS_SESSION_TOKEN)
        
        elif self.API_PROVIDER == 'vertex' and all([
            self.VERTEX_REGION,
            self.VERTEX_PROJECT_ID
        ]):
            # Type checks already done by the all() condition above
            os.environ['CLOUD_ML_REGION'] = str(self.VERTEX_REGION)
            os.environ['ANTHROPIC_VERTEX_PROJECT_ID'] = str(self.VERTEX_PROJECT_ID)


# Create global configuration instance
config = EnvironmentConfig()