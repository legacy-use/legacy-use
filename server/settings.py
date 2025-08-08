import json
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from server.config.env_file import write_to_env_file

ROOT_DIR = Path(__file__).parent.parent
ENV_FILE_PATH = ROOT_DIR / '.env'
ENV_LOCAL_FILE_PATH = ROOT_DIR / '.env.local'


def get_setting_env_file():
    if 'PYTEST_VERSION' in os.environ:
        print('Settings: Using test environment')
        return [ROOT_DIR / '.env.test', ROOT_DIR / '.env.template']

    return [ENV_FILE_PATH, ENV_LOCAL_FILE_PATH]


class AwsSecretsManagerSource(PydanticBaseSettingsSource):
    """
    A pydantic-settings source that loads settings from AWS Secrets Manager.
    """

    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        self.secret_name = 'legacy-use-settings'
        self.region_name = os.getenv('AWS_DEFAULT_REGION', 'eu-central-1')
        self.secrets = self._load_secrets()

    def _load_secrets(self) -> dict[str, Any]:
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager', region_name=self.region_name
        )
        try:
            get_secret_value_response = client.get_secret_value(
                SecretId=self.secret_name
            )
        except (ClientError, NoCredentialsError) as e:
            # You can add more specific error handling here if needed
            print(f'Could not load settings from AWS Secrets Manager: {e}')
            return {}

        secret_string = get_secret_value_response['SecretString']
        return json.loads(secret_string)

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str] | None:
        return self.secrets.get(field_name), field_name

    def __call__(self) -> dict[str, Any]:
        return self.secrets


class Settings(BaseSettings):
    FASTAPI_SERVER_HOST: str = '0.0.0.0'
    FASTAPI_SERVER_PORT: int = 8088

    DATABASE_URL: str = 'postgresql://postgres:postgres@localhost:5432/legacy_use'
    ALEMBIC_CONFIG_PATH: str = 'server/alembic.ini'

    # Database connection pooling settings
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 2
    DATABASE_POOL_TIMEOUT: int = 10
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_POOL_PRE_PING: bool = True

    API_KEY_NAME: str = 'X-API-Key'

    # Maximum number of tokens (input + output) allowed per job
    TOKEN_LIMIT: int = 500000

    GOOGLE_GENAI_API_KEY: str | None = None
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            AwsSecretsManagerSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()  # type: ignore
