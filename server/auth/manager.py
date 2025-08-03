"""User manager for FastAPI Users with hybrid authentication support."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from server.database.models import User
from server.database import db_shared
from server.settings import settings


class UserManager(BaseUserManager[User, UUID]):
    """Custom user manager with hybrid authentication support."""

    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Handle post-registration tasks."""
        print(f'User {user.id} has registered.')

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Handle forgot password (disabled for this implementation)."""
        print(f'User {user.id} has forgot their password. Reset token: {token}')

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Handle email verification (disabled for this implementation)."""
        print(f'Verification requested for user {user.id}. Verification token: {token}')


def get_user_db():
    """Get user database session."""
    session = db_shared.Session()
    try:
        yield SQLAlchemyUserDatabase(session, User)
    finally:
        session.close()


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Get user manager instance."""
    yield UserManager(user_db)


# JWT Authentication
bearer_transport = BearerTransport(tokenUrl='auth/jwt/login')


def get_jwt_strategy() -> JWTStrategy:
    """Get JWT strategy for authentication."""
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=3600,  # 1 hour
    )


jwt_authentication = AuthenticationBackend(
    name='jwt',
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPI Users instance
fastapi_users = FastAPIUsers[User, UUID](
    get_user_manager,
    [jwt_authentication],
)

# Current user dependency
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
