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

    API_KEY: str = 'not-secure-api-key'
    VITE_API_KEY: str | None = None
    API_KEY_NAME: str = 'X-API-Key'

    API_PROVIDER: str = 'anthropic'

    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str | None = None
    AWS_SESSION_TOKEN: str | None = None

    ANTHROPIC_API_KEY: str | None = None

    VERTEX_REGION: str | None = None
    VERTEX_PROJECT_ID: str | None = None

    GOOGLE_GENAI_API_KEY: str | None = None

    LEGACYUSE_PROXY_BASE_URL: str = 'https://api.legacy-use.com/'
    LEGACYUSE_PROXY_API_KEY: str | None = None

    ENVIRONMENT: str = 'development'
    API_SENTRY_DSN: str | None = None
    VITE_SENTRY_DSN_UI: str | None = None

    VITE_PUBLIC_POSTHOG_HOST: str = 'https://eu.i.posthog.com'
    VITE_PUBLIC_POSTHOG_KEY: str = 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8'
    VITE_PUBLIC_DISABLE_TRACKING: bool = False

    LOG_RETENTION_DAYS: int = 7
    SHOW_DOCS: bool = True
    HIDE_INTERNAL_API_ENDPOINTS_IN_DOC: bool = False

    model_config = SettingsConfigDict(
        env_file=get_setting_env_file(),
        extra='allow',
    )

    def __setattr__(self, name: str, value: Any) -> None:
        """Override setter to also write changes to .env.local file"""
        super().__setattr__(name, value)
        write_to_env_file(ENV_LOCAL_FILE_PATH, name, value)


settings = Settings()  # type: ignore
