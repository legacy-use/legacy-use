import logging
import typing as t
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, MutableMapping, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Integer, cast, func, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import text

from server.models.base import CustomAction, JobStatus, JobTerminalStates

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
    def __init__(self):
        """Create a database service using the centralized shared engine.

        Reuses the shared engine and session factory defined in
        `server.database.engine` to avoid multiple connection pools.
        """
        from server.database.engine import (
            SessionLocal as shared_session_factory,
        )
        from server.database.engine import (
            engine as shared_engine,
        )

        self.engine = shared_engine
        self.Session = shared_session_factory

    # Target methods
    def create_target(self, target_data):
        with self.Session() as session:
            target = Target(**target_data)
            session.add(target)
            session.commit()
            return self._to_dict(target)

    def get_target(self, target_id):
        with self.Session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            return self._to_dict(target) if target else None

    def list_targets(self, include_archived=False):
        with self.Session() as session:
            query = session.query(Target)
            if not include_archived:
                query = query.filter(Target.is_archived.is_(False))
            targets = query.all()
            return [self._to_dict(t) for t in targets]

    def update_target(self, target_id, target_data):
        with self.Session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if not target:
                return None

            for key, value in target_data.items():
                setattr(target, key, value)
            target.updated_at = datetime.now()

            session.commit()
            return self._to_dict(target)

    def delete_target(self, target_id):
        with self.Session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                target.is_archived = True
                target.updated_at = datetime.now()
                session.commit()
                return True
            return False

    def hard_delete_target(self, target_id):
        with self.Session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                session.delete(target)
                session.commit()
                return True
            return False

    def unarchive_target(self, target_id):
        with self.Session() as session:
            target = session.query(Target).filter(Target.id == target_id).first()
            if target:
                target.is_archived = False
                target.updated_at = datetime.now()
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

    # Session methods
    def create_session(self, session_data):
        with self.Session() as session:
            new_session = Session(**session_data)
            session.add(new_session)
            session.commit()
            return self._to_dict(new_session)

    def get_session(self, session_id):
        with self.Session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            return self._to_dict(db_session) if db_session else None

    def list_sessions(self, include_archived=False):
        with self.Session() as session:
            query = session.query(Session)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]

    def list_target_sessions(self, target_id, include_archived=False):
        """List all sessions for a specific target."""
        with self.Session() as session:
            query = session.query(Session).filter(Session.target_id == target_id)
            if not include_archived:
                query = query.filter(Session.is_archived.is_(False))
            sessions = query.all()
            return [self._to_dict(s) for s in sessions]

    def update_session(self, session_id, session_data):
        with self.Session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if not db_session:
                return None

            for key, value in session_data.items():
                setattr(db_session, key, value)
            db_session.updated_at = datetime.now()

            session.commit()
            return self._to_dict(db_session)

    def delete_session(self, session_id):
        with self.Session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                db_session.is_archived = True
                db_session.updated_at = datetime.now()
                session.commit()
                return True
            return False

    def hard_delete_session(self, session_id):
        with self.Session() as session:
            db_session = session.query(Session).filter(Session.id == session_id).first()
            if db_session:
                session.delete(db_session)
                session.commit()
                return True
            return False

    # Job methods
    def create_job(self, job_data):
        with self.Session() as session:
            job = Job(**job_data)
            session.add(job)
            session.commit()
            return self._to_dict(job)

    def claim_next_job(
        self,
        lease_owner: str,
        lease_seconds: int = 60,
        tenant_schema: str | None = None,
    ):
        """Atomically claim the next runnable job for execution.

        Picks the oldest QUEUED job such that the target has no RUNNING job and
        no PAUSED/ERROR jobs. Uses row locks and an advisory xact lock to
        guarantee only one claim per target across workers. Sets status to RUNNING
        and assigns a short lease to the claiming worker.

        Returns a job dict or None if nothing claimable.
        """
        with self.Session() as session:
            now = datetime.utcnow()
            lease_exp = now + timedelta(seconds=lease_seconds)

            trans = session.begin()
            try:
                JobAlias = sa.orm.aliased(Job)
                JobBlock = sa.orm.aliased(Job)

                exists_running = sa.exists(
                    sa.select(1).where(
                        JobAlias.target_id == Job.target_id,
                        JobAlias.status == 'RUNNING',
                    )
                )
                exists_blocking = sa.exists(
                    sa.select(1).where(
                        JobBlock.target_id == Job.target_id,
                        JobBlock.status.in_(['PAUSED', 'ERROR']),
                    )
                )

                candidate = (
                    session.query(Job)
                    .filter(Job.status == 'QUEUED')
                    .filter(~exists_running)
                    .filter(~exists_blocking)
                    .order_by(Job.created_at)
                    .with_for_update(skip_locked=True)
                    .first()
                )

                if not candidate:
                    trans.commit()
                    return None

                target_id = str(candidate.target_id)
                # Per-tenant advisory lock on target
                locked = session.execute(
                    text(
                        'SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 42))'
                    ),
                    {'key': (tenant_schema or '') + ':' + target_id},
                ).scalar()

                if not locked:
                    trans.rollback()
                    return None

                # Transition to RUNNING with lease, clear any stale cancel requests
                candidate.status = 'RUNNING'
                candidate.updated_at = now
                candidate.lease_owner = lease_owner
                candidate.lease_expires_at = lease_exp
                candidate.cancel_requested = False

                session.commit()
                result = self._to_dict(candidate)
                return result
            except Exception:
                trans.rollback()
                raise

    def expire_stale_running_jobs(self) -> list[dict]:
        """Mark RUNNING jobs with expired or missing leases as ERROR.

        Returns a list of affected job dicts.
        """
        with self.Session() as session:
            now = datetime.utcnow()
            stale_jobs = (
                session.query(Job)
                .filter(
                    Job.status == 'RUNNING',
                    or_(Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
                )
                .all()
            )
            affected = []
            for job in stale_jobs:
                job.status = 'ERROR'
                job.error = 'Lease expired; worker likely terminated'
                job.completed_at = now
                job.updated_at = now
                job.lease_owner = None
                job.lease_expires_at = None
                affected.append(self._to_dict(job))
            # Always finalize the transaction to avoid leaving an open txn when
            # this method is used alongside other operations on the same Session
            # (e.g., claim_next_job starts its own explicit transaction).
            # Committing with no changes is a no-op and safely ends the transaction.
            session.commit()
            return affected

    def renew_job_lease(
        self, job_id: UUID, lease_owner: str, lease_seconds: int = 60
    ) -> bool:
        """Extend the lease for a RUNNING job if owned by this worker."""
        with self.Session() as session:
            now = datetime.utcnow()
            lease_exp = now + timedelta(seconds=lease_seconds)
            job = (
                session.query(Job)
                .filter(
                    Job.id == job_id,
                    Job.status == 'RUNNING',
                    Job.lease_owner == lease_owner,
                )
                .first()
            )
            if not job:
                return False
            job.lease_expires_at = lease_exp
            job.updated_at = now
            session.commit()
            return True

    def get_job(self, job_id):
        with self.Session() as session:
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

    def list_jobs(
        self,
        limit: int = 10,
        offset: int = 0,
        filters: dict = None,
        include_http_exchanges: bool = False,
    ):
        with self.Session() as session:
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

            # Optionally include http exchanges for all jobs in one query (always trimmed)
            if include_http_exchanges and job_dicts:
                job_id_list = [j['id'] for j in job_dicts]

                columns = [
                    JobLog.id,
                    JobLog.job_id,
                    JobLog.timestamp,
                    JobLog.log_type,
                    JobLog.content_trimmed,
                ]
                logs = (
                    session.query(*columns)
                    .filter(
                        JobLog.log_type == 'http_exchange',
                        JobLog.job_id.in_(job_id_list),
                    )
                    .order_by(JobLog.timestamp)
                    .all()
                )

                exchanges_by_job = {}
                for log in logs:
                    entry = self._to_http_exchange_trimmed_dict(log)
                    exchanges_by_job.setdefault(log.job_id, []).append(entry)

                # Attach grouped exchanges to their respective job dicts
                for job_dict in job_dicts:
                    job_dict['http_exchanges'] = exchanges_by_job.get(
                        job_dict['id'], []
                    )

            return job_dicts

    def list_session_jobs(
        self,
        session_id,
        limit: int = 10,
        offset: int = 0,
        status: Optional[JobStatus] = None,
    ):
        """
        List jobs for a session with optional status filtering.

        Args:
            session_id: The session ID to list jobs for
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            status: Optional status filter (e.g., 'running', 'success', 'error')
        """
        with self.Session() as session:
            query = session.query(Job).filter(Job.session_id == session_id)

            # Apply status filter if provided
            if status:
                query = query.filter(Job.status == status.value)

            # Sort by created_at descending and apply pagination
            query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)

            jobs = query.all()
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
        with self.Session() as session:
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
        with self.Session() as session:
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
        with self.Session() as session:
            return session.query(Job).filter(Job.target_id == target_id).count()

    def count_jobs(self, filters: dict = None):
        with self.Session() as session:
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

    def update_job(self, job_id, job_data, update_session=True):
        """
        Update job and optionally update session's last_job_time for terminal states.

        Args:
            job_id: The job ID to update
            job_data: Dictionary of job fields to update
            update_session: Whether to update session's last_job_time for terminal states (default: True)
        """

        with self.Session() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            for key, value in job_data.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()

            session.commit()
            job_dict = self._to_dict(job)

            # If update_session is True and this is a terminal state, update session's last_job_time
            if update_session and job_dict and job_dict.get('session_id'):
                status = job_data.get('status')
                if status and status in JobTerminalStates:
                    self.update_session(
                        job_dict['session_id'],
                        {'last_job_time': datetime.now()},
                    )

            return job_dict

    def update_job_status(self, job_id, status):
        """Update job status (convenience method that uses update_job)."""
        return self.update_job(
            job_id,
            {'status': status, 'updated_at': datetime.now(timezone.utc)},
            update_session=True,
        )

    def request_job_cancel(self, job_id: UUID) -> bool:
        """Set cancel_requested=true for a job regardless of which worker owns it."""
        with self.Session() as session:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return False
            job.cancel_requested = True
            job.updated_at = datetime.utcnow()
            session.commit()
            return True

    def is_job_cancel_requested(self, job_id: UUID) -> bool:
        with self.Session() as session:
            value = (
                session.query(Job.cancel_requested).filter(Job.id == job_id).scalar()
            )
            return bool(value)

    # Job Log methods
    def create_job_log(self, log_data):
        with self.Session() as session:
            log = JobLog(**log_data)
            session.add(log)
            session.commit()
            return self._to_dict(log)

    def list_job_logs(self, job_id, exclude_http_exchanges=True):
        with self.Session() as session:
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
        with self.Session() as session:
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

                # Convert to dictionaries using the centralized helper for trimmed shape
                return [self._to_http_exchange_trimmed_dict(log) for log in logs]
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
        with self.Session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = (
                session.query(JobLog).filter(JobLog.timestamp < cutoff_date).delete()
            )
            session.commit()
            return deleted_count

    # API Definition Services
    async def get_api_definitions(self, include_archived=False):
        """Get all API definitions."""
        with self.Session() as session:
            # Use ORM query instead of raw SQL
            query = session.query(APIDefinition)
            if not include_archived:
                query = query.filter(APIDefinition.is_archived.is_(False))

            # Execute the query
            api_defs = query.all()
            return api_defs

    async def get_api_definitions_with_versions(self, include_archived=False):
        """Get all API definitions with their versions eagerly loaded."""
        with self.Session() as session:
            # Use ORM query with eager loading of versions
            query = session.query(APIDefinition).options(
                joinedload(APIDefinition.versions)
            )
            if not include_archived:
                query = query.filter(APIDefinition.is_archived.is_(False))

            # Execute the query
            api_defs = query.all()
            return api_defs

    async def get_api_definition(self, api_definition_id=None, name=None):
        """Get an API definition by ID or name."""
        with self.Session() as session:
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
        with self.Session() as session:
            api_definition = APIDefinition(name=name, description=description)
            session.add(api_definition)
            session.commit()
            return self._to_dict(api_definition)

    async def update_api_definition(self, api_definition_id, **kwargs):
        """Update an API definition."""
        logger = logging.getLogger(__name__)
        logger.info(f'Updating API definition with ID: {api_definition_id}')
        logger.info(f'Update parameters: {kwargs}')

        with self.Session() as session:
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
        with self.Session() as session:
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

    # API Definition Version Services
    async def get_api_definition_versions(
        self, api_definition_id, include_inactive=False
    ):
        """Get all versions of an API definition."""
        with self.Session() as session:
            query = session.query(APIDefinitionVersion).filter(
                APIDefinitionVersion.api_definition_id == api_definition_id
            )
            if not include_inactive:
                query = query.filter(APIDefinitionVersion.is_active)
            return query.all()

    async def get_api_definition_version(self, version_id):
        """Get an API definition version by ID."""
        with self.Session() as session:
            return (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )

    async def get_active_api_definition_version(self, api_definition_id):
        """Get the active version of an API definition."""
        with self.Session() as session:
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
        with self.Session() as session:
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
        custom_actions: Dict[str, CustomAction] = {},
        is_active=True,
    ):
        """Create a new API definition version."""
        with self.Session() as session:
            # If this is active, deactivate all other versions
            if is_active:
                session.query(APIDefinitionVersion).filter(
                    APIDefinitionVersion.api_definition_id == api_definition_id,
                    APIDefinitionVersion.is_active,
                ).update({APIDefinitionVersion.is_active: False})

            def _serialize_custom_actions(actions):
                if not actions:
                    return {}
                result = {}
                for k, v in actions.items():
                    if isinstance(v, dict):
                        result[k] = v
                    elif hasattr(v, 'model_dump'):
                        result[k] = v.model_dump()
                    else:
                        result[k] = dict(v)
                return result

            api_definition_version = APIDefinitionVersion(
                api_definition_id=api_definition_id,
                version_number=version_number,
                parameters=parameters,
                prompt=prompt,
                prompt_cleanup=prompt_cleanup,
                response_example=response_example,
                is_active=is_active,
                custom_actions=_serialize_custom_actions(custom_actions),
            )
            session.add(api_definition_version)
            session.commit()
            return self._to_dict(api_definition_version)

    async def update_api_definition_version(self, version_id, **kwargs):
        """Update an API definition version."""
        with self.Session() as session:
            api_definition_version = (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .one_or_none()
            )
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
        with self.Session() as session:
            # Include archived APIs in the search
            return (
                session.query(APIDefinition).filter(APIDefinition.name == name).first()
            )

    async def get_active_api_definition_version_by_name(self, name):
        """Get the active version of an API definition by name."""
        api_definition = await self.get_api_definition_by_name(name)
        if not api_definition:
            return None

        return await self.get_active_api_definition_version(api_definition.id)

    async def get_next_version_number(self, api_definition_id):
        """Get the next version number for an API definition."""
        with self.Session() as session:
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
        result = {}
        for c in obj.__table__.columns:
            value = getattr(obj, c.name)
            # Handle enum serialization
            if hasattr(value, 'value'):
                result[c.name] = value.value
            else:
                result[c.name] = value
        return result

    def _to_http_exchange_trimmed_dict(self, log_row):
        """Return a trimmed HTTP exchange log dict with 'content' set to trimmed content.

        Expects a row or ORM object that has attributes: id, job_id, timestamp, log_type, content_trimmed.
        """
        return {
            'id': log_row.id,
            'job_id': log_row.job_id,
            'timestamp': log_row.timestamp,
            'log_type': log_row.log_type,
            'content': log_row.content_trimmed
            if getattr(log_row, 'content_trimmed', None) is not None
            else {},
        }

    def get_session_job(self, session_id, job_id):
        with self.Session() as session:
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

    # --- Job Message Methods (New) ---
    def get_next_message_sequence(self, job_id: UUID) -> int:
        """Get the next sequence number for a job's messages."""
        with self.Session() as session:
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
        with self.Session() as session:
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

    def get_job_messages(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all messages for a specific job, ordered by sequence."""
        with self.Session() as session:
            messages = (
                session.query(JobMessage)
                .filter(JobMessage.job_id == job_id)
                .order_by(JobMessage.sequence.asc())
                .all()
            )
            return [self._to_dict(msg) for msg in messages]

    def count_job_messages(self, job_id: UUID) -> int:
        """Count the number of messages for a specific job."""
        with self.Session() as session:
            count = (
                session.query(func.count(JobMessage.id))
                .filter(JobMessage.job_id == job_id)
                .scalar()
            )
            return count or 0  # Return 0 if count is None (no messages)

    # --- End Job Message Methods ---

    # --- Tenant Methods ---
    def create_tenant(self, tenant_data):
        """Create a new tenant."""
        with self.Session() as session:
            tenant = Tenant(**tenant_data)
            session.add(tenant)
            session.commit()
            return self._to_dict(tenant)

    def get_tenant(self, tenant_id):
        """Get a tenant by ID."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            return self._to_dict(tenant) if tenant else None

    def get_tenant_by_host(self, host):
        """Get a tenant by host."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.host == host).first()
            return self._to_dict(tenant) if tenant else None

    def get_tenant_by_schema(self, schema):
        """Get a tenant by schema name."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.schema == schema).first()
            return self._to_dict(tenant) if tenant else None

    def list_tenants(self, include_inactive=False):
        """List all tenants."""
        with self.Session() as session:
            query = session.query(Tenant)
            if not include_inactive:
                query = query.filter(Tenant.is_active.is_(True))
            tenants = query.all()
            return [self._to_dict(t) for t in tenants]

    def update_tenant(self, tenant_id, tenant_data):
        """Update a tenant."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return None

            for key, value in tenant_data.items():
                setattr(tenant, key, value)
            tenant.updated_at = datetime.now()

            session.commit()
            return self._to_dict(tenant)

    def delete_tenant(self, tenant_id):
        """Soft delete a tenant by setting is_active to False."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                tenant.is_active = False
                tenant.updated_at = datetime.now()
                session.commit()
                return True
            return False

    def hard_delete_tenant(self, tenant_id):
        """Hard delete a tenant."""
        with self.Session() as session:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                session.delete(tenant)
                session.commit()
                return True
            return False

    # --- End Tenant Methods ---

    def find_ready_session_for_target(self, target_id: UUID) -> Dict[str, Any] | None:
        """Find an available 'ready' and not archived session for the target."""
        with self.Session() as session:
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

    def has_initializing_session_for_target(self, target_id: UUID) -> bool:
        """Check if there's any session in 'initializing' state for this target."""
        with self.Session() as session:
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

    def has_active_session_for_target(self, target_id: UUID) -> Dict[str, Any]:
        """Check if there's any active (non-archived) session for this target."""
        with self.Session() as session:
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

    # Custom Actions Methods
    def get_custom_actions(self, version_id: str) -> Dict[str, Dict[str, CustomAction]]:
        """Get custom actions for an API definition version with validation.

        Args:
            version_id: The ID of the API definition version

        Returns:
            Dict of validated custom actions where keys are action names
        """
        with self.Session() as session:
            api_version = (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )

            if not api_version:
                print(f'No API version found for version id: {version_id}')
                return {}

            actions_data = getattr(api_version, 'custom_actions', None) or {}

            if not isinstance(actions_data, dict):
                actions_data = {}
            validated_actions = {}

            for action_name, action_data in actions_data.items():
                try:
                    action = CustomAction(**action_data)
                    validated_actions[action_name] = action.model_dump()
                except Exception as e:
                    # Log validation error but don't fail
                    logging.warning(
                        f"Invalid custom action data for '{action_name}': {action_data}, error: {e}"
                    )
                    continue
            return validated_actions

    def set_custom_actions(
        self, version_id: str, actions: Dict[str, Dict[str, CustomAction]]
    ) -> bool:
        """Set custom actions for an API definition version with validation.

        Args:
            version_id: The ID of the API definition version
            actions: Dict of action dictionaries to validate and store, keyed by action name

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If actions don't match the expected format
        """
        with self.Session() as session:
            api_version = (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )

            if not api_version:
                return False

            existing = getattr(api_version, 'custom_actions', None)
            if not isinstance(existing, dict):
                setattr(api_version, 'custom_actions', {})
                existing = api_version.custom_actions
            existing_dict = t.cast(MutableMapping[str, Any], existing)

            if not actions:
                existing_dict.clear()
                session.commit()
                return True

            try:
                # Validate each action
                validated_actions = {}
                for action_name, action_data in actions.items():
                    validated_action = CustomAction(**action_data)
                    validated_actions[action_name] = validated_action.model_dump()

                existing_dict.clear()
                existing_dict.update(validated_actions)
                session.commit()
                return True
            except Exception as e:
                raise ValueError(f'Invalid custom actions format: {e}')

    def append_custom_action(self, version_id: str, action: CustomAction) -> bool:
        """Append a custom action to an API definition version."""
        with self.Session() as session:
            api_version = (
                session.query(APIDefinitionVersion)
                .filter(APIDefinitionVersion.id == version_id)
                .first()
            )

            if not api_version:
                print(f'No API version found for version id: {version_id}')
                return False

            existing = getattr(api_version, 'custom_actions', None)
            if not isinstance(existing, dict):
                setattr(api_version, 'custom_actions', {})
                existing = api_version.custom_actions
            existing_dict = t.cast(MutableMapping[str, Any], existing)

            # Upsert in place
            existing_dict[action.name] = action.model_dump()
            session.commit()
            return True
