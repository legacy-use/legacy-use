import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from server.config.env_file import write_to_env_file

ROOT_DIR = Path(__file__).parent.parent
ENV_FILE_PATH = ROOT_DIR / '.env'
ENV_LOCAL_FILE_PATH = ROOT_DIR / '.env.local'


def get_setting_env_file():
    if 'PYTEST_VERSION' in os.environ:
        print('Settings: Using test environment')
        return [ROOT_DIR / '.env.test', ROOT_DIR / '.env.template']

    return [ENV_FILE_PATH, ENV_LOCAL_FILE_PATH]


class Settings(BaseSettings):
    FASTAPI_SERVER_HOST: str = '0.0.0.0'
    FASTAPI_SERVER_PORT: int = 8088

    DATABASE_URL: str = 'postgresql://postgres:postgres@localhost:5432/legacy_use'
    ALEMBIC_CONFIG_PATH: str = 'server/alembic.ini'

    API_KEY_NAME: str = 'X-API-Key'

    # JWT Authentication
    SECRET_KEY: str = 'your-secret-key-change-in-production'

    LEGACYUSE_PROXY_BASE_URL: str = 'https://api.legacy-use.com/'

    ENVIRONMENT: str = 'development'
    API_SENTRY_DSN: str | None = None

    VITE_PUBLIC_POSTHOG_HOST: str = 'https://eu.i.posthog.com'
    VITE_PUBLIC_POSTHOG_KEY: str = 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8'
    VITE_PUBLIC_DISABLE_TRACKING: bool = False

    LOG_RETENTION_DAYS: int = 7
    SHOW_DOCS: bool = True
    HIDE_INTERNAL_API_ENDPOINTS_IN_DOC: bool = False
    API_SLUG_PREFIX: str = '/api'  # Slug prefix for all API routes, e.g. '/slug'. Default is empty (no prefix)

    model_config = SettingsConfigDict(
        env_file=get_setting_env_file(),
        extra='allow',
    )

    def __setattr__(self, name: str, value: Any) -> None:
        """Override setter to also write changes to .env.local file"""
        super().__setattr__(name, value)
        write_to_env_file(ENV_LOCAL_FILE_PATH, name, value)


settings = Settings()  # type: ignore
