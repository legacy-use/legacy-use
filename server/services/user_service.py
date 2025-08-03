"""User management service."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from server.database.models import User, UserTenant

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations."""

    def __init__(self, db_session: Session):
        self.session = db_session

    def _to_dict(self, obj) -> Dict[str, Any]:
        """Convert SQLAlchemy object to dictionary."""
        if obj is None:
            return None

        result = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result

    def create_user(
        self,
        email: str,
        hashed_password: str = None,
        is_admin: bool = False,
        auth_provider: str = 'local',
        auth_provider_user_id: str = None,
    ) -> Dict[str, Any]:
        """Create a new user."""
        try:
            user = User(
                email=email,
                hashed_password=hashed_password,
                is_admin=is_admin,
                auth_provider=auth_provider,
                auth_provider_user_id=auth_provider_user_id,
            )
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
            return self._to_dict(user)
        except Exception as e:
            self.session.rollback()
            logger.error(f'Error creating user: {e}')
            raise

    def get_user(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a user by ID."""
        try:
            user = self.session.query(User).filter(User.id == user_id).first()
            return self._to_dict(user) if user else None
        except Exception as e:
            logger.error(f'Error getting user {user_id}: {e}')
            raise

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email."""
        try:
            user = self.session.query(User).filter(User.email == email).first()
            return self._to_dict(user) if user else None
        except Exception as e:
            logger.error(f'Error getting user by email {email}: {e}')
            raise

    def get_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        try:
            users = self.session.query(User).all()
            return [self._to_dict(user) for user in users]
        except Exception as e:
            logger.error(f'Error getting users: {e}')
            raise

    def update_user(
        self, user_id: UUID, user_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a user."""
        try:
            user = self.session.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            for key, value in user_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            user.updated_at = datetime.utcnow()

            self.session.commit()
            return self._to_dict(user)
        except Exception as e:
            self.session.rollback()
            logger.error(f'Error updating user {user_id}: {e}')
            raise

    def delete_user(self, user_id: UUID) -> bool:
        """Delete a user."""
        try:
            user = self.session.query(User).filter(User.id == user_id).first()
            if user:
                self.session.delete(user)
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.session.rollback()
            logger.error(f'Error deleting user {user_id}: {e}')
            raise

    def assign_user_to_tenant(self, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Assign a user to a tenant."""
        try:
            # Check if assignment already exists
            existing = (
                self.session.query(UserTenant)
                .filter(
                    UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
                )
                .first()
            )

            if existing:
                existing.updated_at = datetime.utcnow()
                user_tenant = existing
            else:
                user_tenant = UserTenant(user_id=user_id, tenant_id=tenant_id)
                self.session.add(user_tenant)

            self.session.commit()
            return self._to_dict(user_tenant)
        except Exception as e:
            self.session.rollback()
            logger.error(f'Error assigning user {user_id} to tenant {tenant_id}: {e}')
            raise

    def get_user_tenants(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get all tenant assignments for a user."""
        try:
            user_tenants = (
                self.session.query(UserTenant)
                .filter(UserTenant.user_id == user_id)
                .all()
            )
            return [self._to_dict(ut) for ut in user_tenants]
        except Exception as e:
            logger.error(f'Error getting user tenants for user {user_id}: {e}')
            raise

    def remove_user_from_tenant(self, user_id: UUID, tenant_id: UUID) -> bool:
        """Remove a user from a tenant."""
        try:
            user_tenant = (
                self.session.query(UserTenant)
                .filter(
                    UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
                )
                .first()
            )

            if user_tenant:
                self.session.delete(user_tenant)
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.session.rollback()
            logger.error(f'Error removing user {user_id} from tenant {tenant_id}: {e}')
            raise

    def get_user_tenant_access(
        self, user_id: UUID, tenant_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get user's access level for a specific tenant."""
        try:
            user_tenant = (
                self.session.query(UserTenant)
                .filter(
                    UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
                )
                .first()
            )

            if user_tenant:
                return self._to_dict(user_tenant)
            return None
        except Exception as e:
            logger.error(
                f'Error getting user tenant access for user {user_id} and tenant {tenant_id}: {e}'
            )
            raise
