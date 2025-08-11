import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import Integer, cast, create_engine, func
from sqlalchemy.orm import sessionmaker, joinedload

from server.settings import settings

from .models import (
    APIDefinition,
    APIDefinitionVersion,
    Job,
    JobLog,
    JobMessage,
    Session,
    Target,
    Tenant,
)


class DatabaseService:
    def __init__(self, db_url=None):
        if db_url is None:
            db_url = settings.DATABASE_URL

        self.engine = create_engine(
            db_url,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        )
        self.Session = sessionmaker(bind=self.engine)

    # Target methods
    def create_target(self, target_data):
        session = self.Session()
        try:
            target = Target(**target_data)
            session.add(target)
            session.commit()
            return self._to_dict(target)
        finally:
            session.close()

    def get_target(self, target_id):
        session = self.Session()
        try:
            target = session.query(Target).filter(Target.id == target_id).first()
            return self._to_dict(target) if target else None
        finally:
            session.close()

    def list_targets(self, include_archived=False):
        session = self.Session()
        try:
            query = session.query(Target)
            if not include_archived:
                query = query.filter(Target.is_archived.is_(False))
            targets = query.all()
            return [self._to_dict(t) for t in targets]
        finally:
            session.close()

    def update_target(self, target_id, target_data):
        session = self.Session()
        try:
            target = session.query(Target).filter(Target.id == target_id).first()
            if not target:
                return None

            for key, value in target_data.items():
                setattr(target, key, value)
            target.updated_at = datetime.now()

            session.commit()
            return self._to_dict(target)
        finally:
            session.close()

    def delete_target(self, target_id):
        session = self.Session()
        try:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                target.is_archived = True
                target.updated_at = datetime.now()
                session.commit()
                return True
            return False
        finally:
            session.close()

    def hard_delete_target(self, target_id):
        session = self.Session()
        try:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                session.delete(target)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def unarchive_target(self, target_id):
        session = self.Session()
        try:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                target.is_archived = False
                target.updated_at = datetime.now()
                session.commit()
                return True
            return False
        finally:
            session.close()

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

    # Session methods
    def create_session(self, session_data):
        session = self.Session()
        try:
            new_session = Session(**session_data)
            session.add(new_session)
            session.commit()
            return self._to_dict(new_session)
        finally:
            session.close()

    def get_session(self, session_id):
        session = self.Session()
        try:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            return self._to_dict(db_session) if db_session else None
        finally:
            session.close()

    def list_sessions(self, include_archived=False):
        session = self.Session()
        try:
            query = session.query(Session)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]
        finally:
            session.close()

    def list_target_sessions(self, target_id, include_archived=False):
        """List all sessions for a specific target."""
        session = self.Session()
        try:
            query = session.query(Session).filter(Session.target_id == target_id)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]
        finally:
            session.close()

    def update_session(self, session_id, session_data):
        session = self.Session()
        try:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if not db_session:
                return None

            for key, value in session_data.items():
                setattr(db_session, key, value)
            db_session.updated_at = datetime.now()

            session.commit()
            return self._to_dict(db_session)
        finally:
            session.close()

    def delete_session(self, session_id):
        session = self.Session()
        try:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                db_session.is_archived = True
                db_session.updated_at = datetime.now()
                session.commit()
                return True
            return False
        finally:
            session.close()

    def hard_delete_session(self, session_id):
        session = self.Session()
        try:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                session.delete(db_session)
                session.commit()
                return True
            return False
        finally:
            session.close()

    # Job methods
    def create_job(self, job_data):
        session = self.Session()
        try:
            job = Job(**job_data)
            session.add(job)
            session.commit()
            return self._to_dict(job)
        finally:
            session.close()

    def get_job(self, job_id):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def list_jobs(self, limit: int = 10, offset: int = 0, filters: dict = None):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def list_target_jobs(self, target_id, limit: int = 10, offset: int = 0):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def list_session_jobs(self, session_id, limit: int = 10, offset: int = 0):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def list_jobs_by_status_and_target(
        self, target_id, statuses, limit: int = 100, offset: int = 0
    ):
        """List jobs by status and target."""
        session = self.Session()
        try:
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
        finally:
            session.close()

    def get_target_job(self, target_id, job_id):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def count_target_jobs(self, target_id):
        session = self.Session()
        try:
            return session.query(Job).filter(Job.target_id == target_id).count()
        finally:
            session.close()

    def count_jobs(self, filters: dict = None):
        session = self.Session()
        try:
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
        finally:
            session.close()

    def update_job(self, job_id, job_data):
        session = self.Session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            for key, value in job_data.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()

            session.commit()
            return self._to_dict(job)
        finally:
            session.close()

    def update_job_status(self, job_id, status):
        return self.update_job(job_id, {'status': status})

    # Job Log methods
    def create_job_log(self, log_data):
        session = self.Session()
        try:
            log = JobLog(**log_data)
            session.add(log)
            session.commit()
            return self._to_dict(log)
        finally:
            session.close()

    def list_job_logs(self, job_id, exclude_http_exchanges=True):
        session = self.Session()
        try:
            query = session.query(JobLog).filter(JobLog.job_id == job_id)
            if exclude_http_exchanges:
                query = query.filter(JobLog.log_type != 'http_exchange')
            logs = query.order_by(JobLog.timestamp).all()
            return [self._to_dict(log) for log in logs]
        finally:
            session.close()

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
        session = self.Session()
        try:
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
        finally:
            session.close()

    def prune_old_logs(self, days=7):
        """Delete logs older than the specified number of days."""
        session = self.Session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = (
                session.query(JobLog).filter(JobLog.timestamp < cutoff_date).delete()
            )
            session.commit()
            return deleted_count
        finally:
            session.close()

    # API Definition Services
    async def get_api_definitions(self, include_archived=False):
        """Get all API definitions."""
        session = self.Session()
        try:
            # Use ORM query instead of raw SQL
            query = session.query(APIDefinition)
            if not include_archived:
                query = query.filter(APIDefinition.is_archived.is_(False))

            # Execute the query
            api_defs = query.all()
            return api_defs
        finally:
            session.close()

    async def get_api_definitions_with_versions(self, include_archived=False):
        """Get all API definitions with their versions eagerly loaded."""
        session = self.Session()
        try:
            # Use ORM query with eager loading of versions
            query = session.query(APIDefinition).options(
                joinedload(APIDefinition.versions)
            )
            if not include_archived:
                query = query.filter(APIDefinition.is_archived.is_(False))

            # Execute the query
            api_defs = query.all()
            return api_defs
        finally:
            session.close()

    async def get_api_definition(self, api_definition_id=None, name=None):
        """Get an API definition by ID or name."""
        session = self.Session()
        try:
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
        finally:
            session.close()

    async def create_api_definition(self, name, description):
        """Create a new API definition."""
        session = self.Session()
        try:
            api_definition = APIDefinition(name=name, description=description)
            session.add(api_definition)
            session.commit()
            return self._to_dict(api_definition)
        finally:
            session.close()

    async def update_api_definition(self, api_definition_id, **kwargs):
        """Update an API definition."""
        logger = logging.getLogger(__name__)
        logger.info(f'Updating API definition with ID: {api_definition_id}')
        logger.info(f'Update parameters: {kwargs}')

        session = self.Session()
        try:
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
        finally:
            session.close()

    async def archive_api_definition(self, api_definition_id):
        """Archive an API definition."""
        logger = logging.getLogger(__name__)

        # Use ORM instead of direct SQL queries
        session = self.Session()
        try:
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
        finally:
            session.close()

    # API Definition Version Services
    async def get_api_definition_versions(
        self, api_definition_id, include_inactive=False
    ):
        """Get all versions of an API definition."""
        session = self.Session()
        try:
            query = session.query(APIDefinitionVersion).filter(
                APIDefinitionVersion.api_definition_id == api_definition_id
            )
            if not include_inactive:
                query = query.filter(APIDefinitionVersion.is_active)
            return query.all()
        finally:
            session.close()

    async def get_api_definition_version(self, version_id):
        """Get an API definition version by ID."""
        session = self.Session()
        try:
            return (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )
        finally:
            session.close()

    async def get_active_api_definition_version(self, api_definition_id):
        """Get the active version of an API definition."""
        session = self.Session()
        try:
            return (
                session.query(APIDefinitionVersion)
                .filter(
                    APIDefinitionVersion.api_definition_id == api_definition_id,
                    APIDefinitionVersion.is_active,
                )
                .first()
            )
        finally:
            session.close()

    async def get_latest_api_definition_version(self, api_definition_id):
        """Get the latest version of an API definition, regardless of active status."""
        session = self.Session()
        try:
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
        finally:
            session.close()

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
        session = self.Session()
        try:
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
        finally:
            session.close()

    async def update_api_definition_version(self, version_id, **kwargs):
        """Update an API definition version."""
        session = self.Session()
        try:
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
        finally:
            session.close()

    async def get_api_definition_by_name(self, name):
        """Get an API definition by name."""
        session = self.Session()
        try:
            # Include archived APIs in the search
            return (
                session.query(APIDefinition).filter(APIDefinition.name == name).first()
            )
        finally:
            session.close()

    async def get_active_api_definition_version_by_name(self, name):
        """Get the active version of an API definition by name."""
        session = self.Session()
        try:
            api_definition = await self.get_api_definition_by_name(name)
            if not api_definition:
                return None

            return await self.get_active_api_definition_version(api_definition.id)
        finally:
            session.close()

    async def get_next_version_number(self, api_definition_id):
        """Get the next version number for an API definition."""
        session = self.Session()
        try:
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
        finally:
            session.close()

    def _to_dict(self, obj):
        if obj is None:
            return None
        result = {}
        for c in obj.__table__.columns:
            value = getattr(obj, c.name)
            # Handle enum serialization
            if hasattr(value, 'value'):
                result[c.name] = value.value
            else:
                result[c.name] = value
        return result

    def get_session_job(self, session_id, job_id):
        session = self.Session()
        try:
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
        finally:
            session.close()

    # --- Job Message Methods (New) ---
    def get_next_message_sequence(self, job_id: UUID) -> int:
        """Get the next sequence number for a job's messages."""
        session = self.Session()
        try:
            max_sequence = (
                session.query(func.max(JobMessage.sequence))
                .filter(JobMessage.job_id == job_id)
                .scalar()
            )
            return (max_sequence or 0) + 1
        finally:
            session.close()

    def add_job_message(
        self, job_id: UUID, sequence: int, role: str, content: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Add a new message to a job's history."""
        session = self.Session()
        try:
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
        except Exception as e:
            session.rollback()  # Rollback on error
            logging.error(f'Error adding job message for job {job_id}: {e}')
            raise  # Re-raise the exception after logging
        finally:
            session.close()

    def get_job_messages(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all messages for a specific job, ordered by sequence."""
        session = self.Session()
        try:
            messages = (
                session.query(JobMessage)
                .filter(JobMessage.job_id == job_id)
                .order_by(JobMessage.sequence.asc())
                .all()
            )
            return [self._to_dict(msg) for msg in messages]
        finally:
            session.close()

    def count_job_messages(self, job_id: UUID) -> int:
        """Count the number of messages for a specific job."""
        session = self.Session()
        try:
            count = (
                session.query(func.count(JobMessage.id))
                .filter(JobMessage.job_id == job_id)
                .scalar()
            )
            return count or 0  # Return 0 if count is None (no messages)
        finally:
            session.close()

    # --- End Job Message Methods ---

    # --- Tenant Methods ---
    def create_tenant(self, tenant_data):
        """Create a new tenant."""
        session = self.Session()
        try:
            tenant = Tenant(**tenant_data)
            session.add(tenant)
            session.commit()
            return self._to_dict(tenant)
        finally:
            session.close()

    def get_tenant(self, tenant_id):
        """Get a tenant by ID."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            return self._to_dict(tenant) if tenant else None
        finally:
            session.close()

    def get_tenant_by_host(self, host):
        """Get a tenant by host."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.host == host).first()
            return self._to_dict(tenant) if tenant else None
        finally:
            session.close()

    def get_tenant_by_schema(self, schema):
        """Get a tenant by schema name."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.schema == schema).first()
            return self._to_dict(tenant) if tenant else None
        finally:
            session.close()

    def list_tenants(self, include_inactive=False):
        """List all tenants."""
        session = self.Session()
        try:
            query = session.query(Tenant)
            if not include_inactive:
                query = query.filter(Tenant.is_active.is_(True))
            tenants = query.all()
            return [self._to_dict(t) for t in tenants]
        finally:
            session.close()

    def update_tenant(self, tenant_id, tenant_data):
        """Update a tenant."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return None

            for key, value in tenant_data.items():
                setattr(tenant, key, value)
            tenant.updated_at = datetime.now()

            session.commit()
            return self._to_dict(tenant)
        finally:
            session.close()

    def delete_tenant(self, tenant_id):
        """Soft delete a tenant by setting is_active to False."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                tenant.is_active = False
                tenant.updated_at = datetime.now()
                session.commit()
                return True
            return False
        finally:
            session.close()

    def hard_delete_tenant(self, tenant_id):
        """Hard delete a tenant."""
        session = self.Session()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                session.delete(tenant)
                session.commit()
                return True
            return False
        finally:
            session.close()

    # --- End Tenant Methods ---

    def find_ready_session_for_target(self, target_id: UUID) -> Dict[str, Any] | None:
        """Find an available 'ready' and not archived session for the target."""
        session = self.Session()
        try:
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
        except Exception as e:
            logging.error(  # Use logging instead of logger for class methods
                f'Error finding available session for target {target_id}: {e}',
                exc_info=True,
            )
            return None
        finally:
            session.close()

    def has_initializing_session_for_target(self, target_id: UUID) -> bool:
        """Check if there's any session in 'initializing' state for this target."""
        session = self.Session()
        try:
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
        except Exception as e:
            logging.error(  # Use logging instead of logger for class methods
                f'Error checking initializing session for target {target_id}: {e}',
                exc_info=True,
            )
            return False  # Assume not initializing if error occurs
        finally:
            session.close()

    def has_active_session_for_target(self, target_id: UUID) -> Dict[str, Any]:
        """Check if there's any active (non-archived) session for this target."""
        session = self.Session()
        try:
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
        except Exception as e:
            logging.error(  # Use logging instead of logger for class methods
                f'Error checking active session for target {target_id}: {e}',
                exc_info=True,
            )
            return {'has_active_session': False, 'session': None}
        finally:
            session.close()
