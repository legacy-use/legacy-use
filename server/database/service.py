import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import Integer, cast, create_engine, func
from sqlalchemy.orm import sessionmaker

from server.settings import settings
from server.utils.tenant import get_tenant_db_session, TenantContext

from .models import (
    APIDefinition,
    APIDefinitionVersion,
    TenantBase,
    Job,
    JobLog,
    JobMessage,
    Session,
    Target,
    TenantModel,
)


class DatabaseService:
    def __init__(self, db_url=None, tenant_schema=None):
        if db_url is None:
            db_url = settings.DATABASE_URL

        self.db_url = db_url
        self.tenant_schema = tenant_schema
        self.engine = create_engine(db_url)
        
        # Initialize shared schema on startup
        self._initialize_shared_schema()
        
        # Set up session maker based on tenant
        if tenant_schema:
            schema_translate_map = {'tenant': tenant_schema}
            connectable = self.engine.execution_options(schema_translate_map=schema_translate_map)
        else:
            connectable = self.engine
        
        self.Session = sessionmaker(bind=connectable)

    def _initialize_shared_schema(self):
        """Initialize shared schema and tables if they don't exist."""
        try:
            from server.utils.tenant import initialize_shared_schema
            initialize_shared_schema()
        except Exception as e:
            logging.warning(f"Could not initialize shared schema: {e}")

    def get_session(self):
        """Get a database session with proper tenant context."""
        if self.tenant_schema:
            return TenantContext(self.tenant_schema)
        else:
            return get_tenant_db_session()

    # Tenant management methods
    def create_tenant(self, tenant_data: dict) -> dict:
        """Create a new tenant with secure API key storage."""
        from server.utils.tenant import (
            generate_api_key, 
            hash_api_key, 
            generate_schema_name,
            create_tenant_schema
        )
        
        # Generate secure API key
        api_key = generate_api_key()
        api_key_hash, salt = hash_api_key(api_key)
        
        # Generate schema name
        schema_name = generate_schema_name(tenant_data['subdomain'])
        
        with get_tenant_db_session() as session:
            # Create tenant record
            tenant = TenantModel(
                name=tenant_data['name'],
                subdomain=tenant_data['subdomain'],
                schema_name=schema_name,
                api_key_hash=api_key_hash,
                api_key_salt=salt,
                settings=tenant_data.get('settings', {})
            )
            session.add(tenant)
            session.commit()
            
            # Create tenant schema and tables
            create_tenant_schema(schema_name)
            
            tenant_dict = self._to_dict(tenant)
            # Include the plain text API key in response (only time it's returned)
            tenant_dict['api_key'] = api_key
            return tenant_dict

    def get_tenant(self, tenant_id: UUID) -> Optional[dict]:
        """Get tenant by ID."""
        with get_tenant_db_session() as session:
            tenant = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            return self._to_dict(tenant) if tenant else None

    def list_tenants(self, include_inactive=False) -> List[dict]:
        """List all tenants."""
        with get_tenant_db_session() as session:
            query = session.query(TenantModel)
            if not include_inactive:
                query = query.filter(TenantModel.status == 'active')
            tenants = query.all()
            return [self._to_dict(t) for t in tenants]

    def update_tenant(self, tenant_id: UUID, tenant_data: dict) -> Optional[dict]:
        """Update tenant information."""
        with get_tenant_db_session() as session:
            tenant = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            if not tenant:
                return None

            for key, value in tenant_data.items():
                if hasattr(tenant, key) and key not in ['api_key_hash', 'api_key_salt']:
                    setattr(tenant, key, value)
            tenant.updated_at = datetime.now()

            session.commit()
            return self._to_dict(tenant)

    def regenerate_tenant_api_key(self, tenant_id: UUID) -> Optional[dict]:
        """Regenerate API key for a tenant."""
        from server.utils.tenant import generate_api_key, hash_api_key
        
        api_key = generate_api_key()
        api_key_hash, salt = hash_api_key(api_key)
        
        with get_tenant_db_session() as session:
            tenant = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            if not tenant:
                return None

            tenant.api_key_hash = api_key_hash
            tenant.api_key_salt = salt
            tenant.updated_at = datetime.now()

            session.commit()
            
            tenant_dict = self._to_dict(tenant)
            tenant_dict['api_key'] = api_key  # Return new API key
            return tenant_dict

    # Target methods (tenant-aware)
    def create_target(self, target_data):
        with self.get_session() as session:
            target = Target(**target_data)
            session.add(target)
            session.commit()
            return self._to_dict(target)

    def get_target(self, target_id):
        with self.get_session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            return self._to_dict(target) if target else None

    def list_targets(self, include_archived=False):
        with self.get_session() as session:
            query = session.query(Target)
            if not include_archived:
                query = query.filter(Target.is_archived.is_(False))
            targets = query.all()
            return [self._to_dict(t) for t in targets]

    def update_target(self, target_id, target_data):
        with self.get_session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if not target:
                return None

            for key, value in target_data.items():
                setattr(target, key, value)
            target.updated_at = datetime.now()

            session.commit()
            return self._to_dict(target)

    def delete_target(self, target_id):
        with self.get_session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                target.is_archived = True
                target.updated_at = datetime.now()
                session.commit()
                return True
            return False

    def hard_delete_target(self, target_id):
        with self.get_session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                session.delete(target)
                session.commit()
                return True
            return False

    def is_target_queue_paused(self, target_id):
        """Check if a target's queue should be paused by looking for jobs in ERROR or PAUSED state.
        Returns a dictionary with blocking status and information.
        """
        from server.models.base import JobStatus

        blocking_states = [JobStatus.ERROR.value, JobStatus.PAUSED.value]

        # Check if any jobs for this target are in blocking states (ERROR or PAUSED)
        blocking_jobs = self.list_jobs_by_status_and_target(
            target_id, blocking_states, limit=100
        )

        # Return detailed information
        return {
            'is_paused': len(blocking_jobs) > 0,
            'blocking_jobs': blocking_jobs,
            'blocking_jobs_count': len(blocking_jobs),
            'blocking_job_ids': [job['id'] for job in blocking_jobs],
        }

    def get_blocking_jobs_for_target(self, target_id, limit: int = 10, offset: int = 0):
        """Get jobs that are blocking the execution queue for a target (jobs in ERROR or PAUSED state).
        Uses is_target_queue_paused as source of truth.
        """
        # Get blocking information from the source of truth
        blocking_info = self.is_target_queue_paused(target_id)

        # Return the blocking jobs with optional limit and offset
        blocking_jobs = blocking_info['blocking_jobs']

        # Apply limit and offset if needed
        if offset > 0 or limit < len(blocking_jobs):
            return blocking_jobs[offset : offset + limit]
        return blocking_jobs

    # Session methods (tenant-aware)
    def create_session(self, session_data):
        with self.get_session() as session:
            new_session = Session(**session_data)
            session.add(new_session)
            session.commit()
            return self._to_dict(new_session)

    def get_session(self, session_id):
        with self.get_session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            return self._to_dict(db_session) if db_session else None

    def list_sessions(self, include_archived=False):
        with self.get_session() as session:
            query = session.query(Session)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]

    def list_target_sessions(self, target_id, include_archived=False):
        """List all sessions for a specific target."""
        with self.get_session() as session:
            query = session.query(Session).filter(Session.target_id == target_id)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]

    def update_session(self, session_id, session_data):
        with self.get_session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if not db_session:
                return None

            for key, value in session_data.items():
                setattr(db_session, key, value)
            db_session.updated_at = datetime.now()

            session.commit()
            return self._to_dict(db_session)

    def delete_session(self, session_id):
        with self.get_session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                db_session.is_archived = True
                db_session.updated_at = datetime.now()
                session.commit()
                return True
            return False

    def hard_delete_session(self, session_id):
        with self.get_session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                session.delete(db_session)
                session.commit()
                return True
            return False

    # Job methods (tenant-aware)
    def create_job(self, job_data):
        with self.get_session() as session:
            job = Job(**job_data)
            session.add(job)
            session.commit()
            return self._to_dict(job)

    def get_job(self, job_id):
        with self.get_session() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            job_dict = self._to_dict(job)

            # Include API definition version ID if available
            if job.api_definition_version_id:
                job_dict['api_definition_version_id'] = str(
                    job.api_definition_version_id
                )

            return job_dict

    def list_jobs(self, limit: int = 10, offset: int = 0, filters: dict = None):
        with self.get_session() as session:
            query = session.query(Job).order_by(Job.created_at.desc())

            # Apply filters if provided
            if filters:
                if 'status' in filters and filters['status']:
                    query = query.filter(Job.status == filters['status'])
                if 'target_id' in filters and filters['target_id']:
                    query = query.filter(Job.target_id == filters['target_id'])
                if 'api_name' in filters and filters['api_name']:
                    query = query.filter(Job.api_name == filters['api_name'])

            jobs = query.offset(offset).limit(limit).all()
            job_dicts = []
            for job in jobs:
                job_dict = self._to_dict(job)
                # Include API definition version ID if available
                if job.api_definition_version_id:
                    job_dict['api_definition_version_id'] = str(
                        job.api_definition_version_id
                    )
                job_dicts.append(job_dict)
            return job_dicts

    def list_target_jobs(self, target_id, limit: int = 10, offset: int = 0):
        with self.get_session() as session:
            jobs = (
                session.query(Job)
                .filter(Job.target_id == target_id)
                .order_by(Job.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            job_dicts = []
            for job in jobs:
                job_dict = self._to_dict(job)
                # Include API definition version ID if available
                if job.api_definition_version_id:
                    job_dict['api_definition_version_id'] = str(
                        job.api_definition_version_id
                    )
                job_dicts.append(job_dict)
            return job_dicts

    def list_session_jobs(self, session_id, limit: int = 10, offset: int = 0):
        with self.get_session() as session:
            jobs = (
                session.query(Job)
                .filter(Job.session_id == session_id)
                .order_by(Job.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            job_dicts = []
            for job in jobs:
                job_dict = self._to_dict(job)
                # Include API definition version ID if available
                if job.api_definition_version_id:
                    job_dict['api_definition_version_id'] = str(
                        job.api_definition_version_id
                    )
                job_dicts.append(job_dict)
            return job_dicts

    def list_jobs_by_status_and_target(
        self, target_id, statuses, limit: int = 100, offset: int = 0
    ):
        """List jobs by status and target."""
        with self.get_session() as session:
            query = session.query(Job).filter(Job.target_id == target_id)

            # Convert status strings to list if needed
            if isinstance(statuses, str):
                statuses = [statuses]

            # Apply status filter if provided
            if statuses:
                query = query.filter(Job.status.in_(statuses))

            # Execute query with limits
            jobs = (
                query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
            )

            # Convert to dictionaries
            job_dicts = []
            for job in jobs:
                job_dict = self._to_dict(job)
                # Include API definition version ID if available
                if job.api_definition_version_id:
                    job_dict['api_definition_version_id'] = str(
                        job.api_definition_version_id
                    )
                job_dicts.append(job_dict)
            return job_dicts

    def get_target_job(self, target_id, job_id):
        with self.get_session() as session:
            job = (
                session.query(Job)
                .filter(Job.target_id == target_id, Job.id == job_id)
                .first()
            )
            if not job:
                return None

            job_dict = self._to_dict(job)

            # Include API definition version ID if available
            if job.api_definition_version_id:
                job_dict['api_definition_version_id'] = str(
                    job.api_definition_version_id
                )

            return job_dict

    def count_target_jobs(self, target_id):
        with self.get_session() as session:
            return session.query(Job).filter(Job.target_id == target_id).count()

    def count_jobs(self, filters: dict = None):
        with self.get_session() as session:
            query = session.query(Job)

            # Apply filters if provided
            if filters:
                if 'status' in filters and filters['status']:
                    query = query.filter(Job.status == filters['status'])
                if 'target_id' in filters and filters['target_id']:
                    query = query.filter(Job.target_id == filters['target_id'])
                if 'api_name' in filters and filters['api_name']:
                    query = query.filter(Job.api_name == filters['api_name'])

            return query.count()

    def update_job(self, job_id, job_data):
        with self.get_session() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            for key, value in job_data.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()

            session.commit()
            return self._to_dict(job)

    def update_job_status(self, job_id, status):
        return self.update_job(job_id, {'status': status})

    # Job Log methods (tenant-aware)
    def create_job_log(self, log_data):
        with self.get_session() as session:
            log = JobLog(**log_data)
            session.add(log)
            session.commit()
            return self._to_dict(log)

    def list_job_logs(self, job_id, exclude_http_exchanges=True):
        with self.get_session() as session:
            query = session.query(JobLog).filter(JobLog.job_id == job_id)
            if exclude_http_exchanges:
                query = query.filter(JobLog.log_type != 'http_exchange')
            logs = query.order_by(JobLog.timestamp).all()
            return [self._to_dict(log) for log in logs]

    def list_job_http_exchanges(self, job_id, use_trimmed=True):
        """
        Get all HTTP exchange logs for a job.

        Args:
            job_id: The job ID
            use_trimmed: Whether to use the trimmed content (without image data)
                         instead of the full content

        Returns:
            List of HTTP exchange logs
        """
        with self.get_session() as session:
            if use_trimmed:
                # Only load necessary columns when using trimmed content
                # We explicitly don't select the 'content' column which can be large
                columns = [
                    JobLog.id,
                    JobLog.job_id,
                    JobLog.timestamp,
                    JobLog.log_type,
                    JobLog.content_trimmed,
                ]
                logs = (
                    session.query(*columns)
                    .filter(JobLog.job_id == job_id, JobLog.log_type == 'http_exchange')
                    .order_by(JobLog.timestamp)
                    .all()
                )

                # Convert to dictionaries and rename content_trimmed to content
                log_dicts = []
                for log in logs:
                    # Convert to dictionary with selected columns only
                    log_dict = {
                        'id': log.id,
                        'job_id': log.job_id,
                        'timestamp': log.timestamp,
                        'log_type': log.log_type,
                    }
                    # Use content_trimmed as content if available, otherwise set empty dict
                    log_dict['content'] = (
                        log.content_trimmed if log.content_trimmed is not None else {}
                    )
                    log_dicts.append(log_dict)
                return log_dicts
            else:
                # Load complete log records including the full content
                logs = (
                    session.query(JobLog)
                    .filter(JobLog.job_id == job_id, JobLog.log_type == 'http_exchange')
                    .order_by(JobLog.timestamp)
                    .all()
                )
                return [self._to_dict(log) for log in logs]

    def prune_old_logs(self, days=7):
        """Delete logs older than the specified number of days."""
        with self.get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = (
                session.query(JobLog).filter(JobLog.timestamp < cutoff_date).delete()
            )
            session.commit()
            return deleted_count

    # API Definition Services (tenant-aware)
    async def get_api_definitions(self, include_archived=False):
        """Get all API definitions."""
        with self.get_session() as session:
            # Use ORM query instead of raw SQL
            query = session.query(APIDefinition)
            if not include_archived:
                query = query.filter(APIDefinition.is_archived.is_(False))

            # Execute the query
            api_defs = query.all()
            return api_defs

    async def get_api_definition(self, api_definition_id=None, name=None):
        """Get an API definition by ID or name."""
        with self.get_session() as session:
            if api_definition_id:
                return (
                    session.query(APIDefinition)
                    .filter(APIDefinition.id == api_definition_id)
                    .first()
                )
            elif name:
                return (
                    session.query(APIDefinition)
                    .filter(APIDefinition.name == name)
                    .first()
                )
            return None

    async def create_api_definition(self, name, description):
        """Create a new API definition."""
        with self.get_session() as session:
            api_definition = APIDefinition(name=name, description=description)
            session.add(api_definition)
            session.commit()
            return self._to_dict(api_definition)

    async def update_api_definition(self, api_definition_id, **kwargs):
        """Update an API definition."""
        logger = logging.getLogger(__name__)
        logger.info(f'Updating API definition with ID: {api_definition_id}')
        logger.info(f'Update parameters: {kwargs}')

        with self.get_session() as session:
            # Get the API definition using ORM
            api_definition = (
                session.query(APIDefinition)
                .filter(APIDefinition.id == api_definition_id)
                .first()
            )
            if not api_definition:
                logger.error(f'API definition with ID {api_definition_id} not found')
                return None

            # Update all provided fields
            for key, value in kwargs.items():
                if hasattr(api_definition, key):
                    logger.info(f'Setting {key} = {value}')
                    setattr(api_definition, key, value)
                else:
                    logger.warning(f'API definition has no attribute {key}')

            # Update the updated_at timestamp
            api_definition.updated_at = datetime.now()
            session.commit()

            # Return the updated object as a dictionary
            return self._to_dict(api_definition)

    async def archive_api_definition(self, api_definition_id):
        """Archive an API definition."""
        logger = logging.getLogger(__name__)

        # Use ORM instead of direct SQL queries
        with self.get_session() as session:
            # Get the API definition
            api_definition = (
                session.query(APIDefinition)
                .filter(APIDefinition.id == api_definition_id)
                .first()
            )
            if not api_definition:
                logger.error(f'API definition with ID {api_definition_id} not found')
                return None

            # Update to archived state
            api_definition.is_archived = True
            api_definition.updated_at = datetime.now()
            session.commit()

            # Return the updated object as a dictionary
            return self._to_dict(api_definition)

    # API Definition Version Services (tenant-aware)
    async def get_api_definition_versions(
        self, api_definition_id, include_inactive=False
    ):
        """Get all versions of an API definition."""
        with self.get_session() as session:
            query = session.query(APIDefinitionVersion).filter(
                APIDefinitionVersion.api_definition_id == api_definition_id
            )
            if not include_inactive:
                query = query.filter(APIDefinitionVersion.is_active)
            return query.all()

    async def get_api_definition_version(self, version_id):
        """Get an API definition version by ID."""
        with self.get_session() as session:
            return (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )

    async def get_active_api_definition_version(self, api_definition_id):
        """Get the active version of an API definition."""
        with self.get_session() as session:
            return (
                session.query(APIDefinitionVersion)
                .filter(
                    APIDefinitionVersion.api_definition_id == api_definition_id,
                    APIDefinitionVersion.is_active,
                )
                .first()
            )

    async def get_latest_api_definition_version(self, api_definition_id):
        """Get the latest version of an API definition, regardless of active status."""
        with self.get_session() as session:
            # Get all versions for this API definition
            versions = (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.api_definition_id == api_definition_id)
                .all()
            )

            if not versions:
                return None

            # Sort versions by version number (descending)
            # Fix: Use a more robust approach with error handling
            def get_version_number(version):
                try:
                    return int(version.version_number)
                except (ValueError, TypeError):
                    # If version_number is not a valid integer, return 0 as fallback
                    return 0

            versions.sort(key=get_version_number, reverse=True)

            # Return the latest version
            return versions[0]

    async def create_api_definition_version(
        self,
        api_definition_id,
        version_number,
        parameters,
        prompt,
        prompt_cleanup,
        response_example,
        is_active=True,
    ):
        """Create a new API definition version."""
        with self.get_session() as session:
            # If this is active, deactivate all other versions
            if is_active:
                session.query(APIDefinitionVersion).filter(
                    APIDefinitionVersion.api_definition_id == api_definition_id,
                    APIDefinitionVersion.is_active,
                ).update({APIDefinitionVersion.is_active: False})

            api_definition_version = APIDefinitionVersion(
                api_definition_id=api_definition_id,
                version_number=version_number,
                parameters=parameters,
                prompt=prompt,
                prompt_cleanup=prompt_cleanup,
                response_example=response_example,
                is_active=is_active,
            )
            session.add(api_definition_version)
            session.commit()
            return self._to_dict(api_definition_version)

    async def update_api_definition_version(self, version_id, **kwargs):
        """Update an API definition version."""
        with self.get_session() as session:
            api_definition_version = await self.get_api_definition_version(version_id)
            if not api_definition_version:
                return None

            # If activating this version, deactivate all others
            if kwargs.get('is_active', False) and not api_definition_version.is_active:
                session.query(APIDefinitionVersion).filter(
                    APIDefinitionVersion.api_definition_id
                    == api_definition_version.api_definition_id,
                    APIDefinitionVersion.is_active,
                ).update({APIDefinitionVersion.is_active: False})

            for key, value in kwargs.items():
                if hasattr(api_definition_version, key):
                    setattr(api_definition_version, key, value)

            api_definition_version.updated_at = datetime.now()
            session.commit()
            return self._to_dict(api_definition_version)

    async def get_api_definition_by_name(self, name):
        """Get an API definition by name."""
        with self.get_session() as session:
            # Include archived APIs in the search
            return (
                session.query(APIDefinition).filter(APIDefinition.name == name).first()
            )

    async def get_active_api_definition_version_by_name(self, name):
        """Get the active version of an API definition by name."""
        with self.get_session() as session:
            api_definition = await self.get_api_definition_by_name(name)
            if not api_definition:
                return None

            return await self.get_active_api_definition_version(api_definition.id)

    async def get_next_version_number(self, api_definition_id):
        """Get the next version number for an API definition."""
        with self.get_session() as session:
            # Get the highest version number for this API definition
            # Use SQLAlchemy's proper syntax for ordering with a cast
            highest_version = (
                session.query(APIDefinitionVersion.version_number)
                .filter(APIDefinitionVersion.api_definition_id == api_definition_id)
                .order_by(cast(APIDefinitionVersion.version_number, Integer).desc())
                .first()
            )

            # If no versions exist, start with 1
            if not highest_version:
                return 1

            # Convert the version number to an integer if it's a string
            try:
                # Use explicit base 10 conversion to ensure proper handling of version numbers
                current_version = int(highest_version[0], 10)
                return current_version + 1
            except ValueError:
                # If it can't be converted to an integer, just return 1
                return 1

    def _to_dict(self, obj):
        if obj is None:
            return None
        result = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        return result

    def get_session_job(self, session_id, job_id):
        with self.get_session() as session:
            job = (
                session.query(Job)
                .filter(Job.session_id == session_id, Job.id == job_id)
                .first()
            )
            if not job:
                return None

            job_dict = self._to_dict(job)

            # Include API definition version ID if available
            if job.api_definition_version_id:
                job_dict['api_definition_version_id'] = str(
                    job.api_definition_version_id
                )

            return job_dict

    # --- Job Message Methods (tenant-aware) ---
    def get_next_message_sequence(self, job_id: UUID) -> int:
        """Get the next sequence number for a job's messages."""
        with self.get_session() as session:
            max_sequence = (
                session.query(func.max(JobMessage.sequence))
                .filter(JobMessage.job_id == job_id)
                .scalar()
            )
            return (max_sequence or 0) + 1

    def add_job_message(
        self, job_id: UUID, sequence: int, role: str, content: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Add a new message to a job's history."""
        with self.get_session() as session:
            # Validate role if necessary (e.g., ensure it's 'user' or 'assistant')
            allowed_roles = ['user', 'assistant']
            if role not in allowed_roles:
                # Log warning or raise error? For now, log and proceed
                logging.warning(
                    f"Attempted to add job message with invalid role '{role}' for job {job_id}"
                )
                # raise ValueError(f"Invalid role: {role}. Must be one of {allowed_roles}")

            new_message = JobMessage(
                job_id=job_id,
                sequence=sequence,
                role=role,
                message_content=content,  # Assuming content is already serialized dict/list
            )
            session.add(new_message)
            session.commit()
            # Refresh to get default values like ID and created_at
            session.refresh(new_message)
            return self._to_dict(new_message)  # Use existing helper if available

    def get_job_messages(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all messages for a specific job, ordered by sequence."""
        with self.get_session() as session:
            messages = (
                session.query(JobMessage)
                .filter(JobMessage.job_id == job_id)
                .order_by(JobMessage.sequence.asc())
                .all()
            )
            return [self._to_dict(msg) for msg in messages]

    def count_job_messages(self, job_id: UUID) -> int:
        """Count the number of messages for a specific job."""
        with self.get_session() as session:
            count = (
                session.query(func.count(JobMessage.id))
                .filter(JobMessage.job_id == job_id)
                .scalar()
            )
            return count or 0  # Return 0 if count is None (no messages)

    # --- End Job Message Methods ---

    def find_ready_session_for_target(self, target_id: UUID) -> Dict[str, Any] | None:
        """Find an available 'ready' and not archived session for the target."""
        with self.get_session() as session:
            # Find a session that is ready and not archived
            available_session = (
                session.query(Session)
                .filter(
                    Session.target_id == target_id,
                    Session.state == 'ready',
                    Session.is_archived.is_(False),
                )
                .first()
            )

            if available_session:
                return self._to_dict(available_session)
            return None

    def has_initializing_session_for_target(self, target_id: UUID) -> bool:
        """Check if there's any session in 'initializing' state for this target."""
        with self.get_session() as session:
            # Find any session that is initializing and not archived
            initializing_session = (
                session.query(Session.id)  # Query for id only for efficiency
                .filter(
                    Session.target_id == target_id,
                    Session.state == 'initializing',
                    Session.is_archived.is_(False),
                )
                .first()
            )
            return initializing_session is not None

    def has_active_session_for_target(self, target_id: UUID) -> Dict[str, Any]:
        """Check if there's any active (non-archived) session for this target."""
        with self.get_session() as session:
            # Find any session that is not archived for this target
            active_session = (
                session.query(Session)
                .filter(
                    Session.target_id == target_id,
                    Session.is_archived.is_(False),
                )
                .first()
            )

            if active_session:
                return {
                    'has_active_session': True,
                    'session': self._to_dict(active_session),
                }
            return {'has_active_session': False, 'session': None}


# Create tenant-aware database service factory
def get_tenant_database_service(tenant_schema: str = None) -> DatabaseService:
    """Factory function to create tenant-aware database service."""
    return DatabaseService(tenant_schema=tenant_schema)
