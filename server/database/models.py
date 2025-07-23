import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TEXT, TypeDecorator

Base = declarative_base()


class UUID(TypeDecorator):
    """UUID Type for SQLite (stores as TEXT)"""

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


class Target(Base):
    __tablename__ = 'targets'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String)
    type = Column(String)
    host = Column(String)
    port = Column(String)
    username = Column(String, nullable=True)
    password = Column(String)
    vpn_config = Column(String, nullable=True)
    vpn_username = Column(String, nullable=True)
    vpn_password = Column(String, nullable=True)
    width = Column(String, nullable=False, default='1024')
    height = Column(String, nullable=False, default='768')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_archived = Column(Boolean, default=False)

    sessions = relationship(
        'Session', back_populates='target', cascade='all, delete-orphan'
    )
    jobs = relationship('Job', back_populates='target', cascade='all, delete-orphan')


class Session(Base):
    """Session model for storing session information."""

    __tablename__ = 'sessions'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    target_id = Column(UUID, ForeignKey('targets.id'), nullable=False)
    status = Column(String, nullable=False, default='created')
    state = Column(String, nullable=False, default='initializing')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_archived = Column(Boolean, default=False)
    archive_reason = Column(
        String, nullable=True
    )  # Reason for archiving: 'user-initiated' or 'auto-cleanup'
    last_job_time = Column(
        DateTime, nullable=True
    )  # Time of the last job run on this session

    # Container information
    container_id = Column(String, nullable=True)  # Store Docker container ID
    container_ip = Column(String, nullable=True)  # Store container IP address

    # Relationships
    target = relationship('Target', back_populates='sessions')
    jobs = relationship('Job', back_populates='session', cascade='all, delete-orphan')


class APIDefinition(Base):
    __tablename__ = 'api_definitions'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_archived = Column(Boolean, default=False)

    # Relationships
    versions = relationship(
        'APIDefinitionVersion',
        back_populates='api_definition',
        cascade='all, delete-orphan',
    )


class APIDefinitionVersion(Base):
    __tablename__ = 'api_definition_versions'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    api_definition_id = Column(UUID, ForeignKey('api_definitions.id'), nullable=False)
    version_number = Column(
        String, nullable=False
    )  # Semantic versioning (e.g., "1.0.0")
    parameters = Column(SQLiteJSON, nullable=False, default=[])
    prompt = Column(String, nullable=False)
    prompt_cleanup = Column(String, nullable=False)
    response_example = Column(SQLiteJSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(
        Boolean, default=True
    )  # Only one version can be active at a time

    # Relationships
    api_definition = relationship('APIDefinition', back_populates='versions')
    jobs = relationship('Job', back_populates='api_definition_version')


class Job(Base):
    __tablename__ = 'jobs'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    target_id = Column(UUID, ForeignKey('targets.id'), nullable=False)
    session_id = Column(UUID, ForeignKey('sessions.id'), nullable=True)
    api_name = Column(String)
    api_definition_version_id = Column(
        UUID, ForeignKey('api_definition_versions.id'), nullable=True
    )
    parameters = Column(SQLiteJSON)
    status = Column(String, default='pending')
    result = Column(SQLiteJSON, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    total_input_tokens = Column(Integer, nullable=True)
    total_output_tokens = Column(Integer, nullable=True)

    target = relationship('Target', back_populates='jobs')
    session = relationship('Session', back_populates='jobs')
    logs = relationship('JobLog', back_populates='job', cascade='all, delete-orphan')
    api_definition_version = relationship('APIDefinitionVersion', back_populates='jobs')
    messages = relationship(
        'JobMessage',
        back_populates='job',
        cascade='all, delete-orphan',
        order_by='JobMessage.sequence',
    )


class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID, ForeignKey('jobs.id'))
    timestamp = Column(DateTime, default=datetime.now)
    log_type = Column(String)  # system, http_exchange, tool_use, message, result, error
    content = Column(SQLiteJSON)
    content_trimmed = Column(
        SQLiteJSON, nullable=True
    )  # Trimmed content without images for lighter processing

    job = relationship('Job', back_populates='logs')


class JobMessage(Base):
    __tablename__ = 'job_messages'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True
    )
    sequence = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    message_content = Column(SQLiteJSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship('Job', back_populates='messages')

    __table_args__ = (Index('ix_jobmessage_job_id_sequence', 'job_id', 'sequence'),)
