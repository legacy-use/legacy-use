from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

from server.models.api_provider import APIProvider

ROOT_DIR = Path(__file__).parent.parent
ENV_FILE_PATH = ROOT_DIR / '.env'


class Settings(BaseSettings):
    FASTAPI_SERVER_HOST: str = '0.0.0.0'
    FASTAPI_SERVER_PORT: int = 8088

    DATABASE_URL: str = 'sqlite:///server/server.db'

    API_KEY: str = 'not-secure-api-key'
    API_KEY_NAME: str = 'X-API-Key'

    API_PROVIDER: APIProvider = APIProvider.ANTHROPIC

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    AWS_SESSION_TOKEN: str | None = None

    ANTHROPIC_API_KEY: str

    VERTEX_REGION: str
    VERTEX_PROJECT_ID: str

    ENVIRONMENT: str = 'development'
    API_SENTRY_DSN: str | None = None

    VITE_PUBLIC_POSTHOG_HOST: str = 'https://eu.i.posthog.com'
    VITE_PUBLIC_POSTHOG_KEY: str = 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8'
    VITE_PUBLIC_DISABLE_TRACKING: bool = False

    LOG_RETENTION_DAYS: int = 7
    SHOW_DOCS: bool = True
    HIDE_INTERNAL_API_ENDPOINTS_IN_DOC: bool = False

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        extra='allow',
    )


settings = Settings()  # type: ignore
