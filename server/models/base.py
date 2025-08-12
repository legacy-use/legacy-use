"""
Base models for the API Gateway.
"""

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Parameter(BaseModel):
    name: str
    type: str
    description: str
    default: Optional[Union[str, List[Any]]] = None


class APIDefinition(BaseModel):
    name: str
    description: str
    parameters: List[Parameter] = []
    response_example: Dict[str, Any] = {}
    is_archived: bool = False


class APIDefinitionRuntime:
    """Runtime API definition class with prompt building capabilities."""

    def __init__(self, data: Dict[str, Any]):
        self.name = data['name']
        self.description = data['description']
        self.parameters = data.get('parameters', [])
        self.prompt = data.get('prompt', '')
        self.prompt_cleanup = data.get('prompt_cleanup', '')
        self.response_example = data.get('response_example', {})
        self.version = data.get('version', '1')
        self.version_id = data.get('version_id')
        self.is_archived = data.get('is_archived', False)

        # Build the full prompt template with instructions
        self.full_prompt_template = self._build_full_prompt_template()

    # TODO: Once a chat function is implemented, split that prompt up. e.g. only give the cleanup prompt once the actual call was successful
    # TODO: Move the prompt template in to seperate file
    def _build_full_prompt_template(self) -> str:
        """Build the full prompt template with cleanup and response example instructions."""
        # Build the full prompt with standard instructions
        prompt_full = f'''{self.prompt}


IMPORTANT INSTRUCTIONS FOR RETURNING RESULTS:


1. When you've found the requested information, you MUST use the extraction tool to return the result. Use these parameters:

   ```
   {{
     "name": "{self.name}",
     "result": {self.response_example}
   }}
   ```

2. The API call will ONLY succeed if:
   - You use the extraction tool (not plain text)
   - You return valid JSON data in the format shown above
   - You end your turn after extraction

3. DO NOT output the JSON directly in text - you must ONLY use the extraction tool.

4. After you've completed the extraction, please perform these steps to return the system to its original state: {self.prompt_cleanup}
'''

        return prompt_full

    def build_prompt(self, job_parameters: Dict[str, Any]) -> str:
        """Build the prompt by substituting parameter values."""
        prompt_text = self.full_prompt_template

        # Add current date to the parameters
        job_parameters = job_parameters.copy()
        job_parameters['now'] = datetime.now()  # TODO: Why is this needed?

        # Replace parameter placeholders with actual values
        for param_name, param_value in job_parameters.items():
            # Support both {{param_name}} and {param_name} placeholder formats
            placeholder_patterns = [
                f'{{{{{param_name}}}}}',  # {{param_name}}
                f'{{{param_name}}}',  # {param_name}
            ]

            for pattern in placeholder_patterns:
                if pattern in prompt_text:
                    # Convert value to string for replacement
                    str_value = str(param_value) if param_value is not None else ''
                    prompt_text = prompt_text.replace(pattern, str_value)

        return prompt_text


class TargetType(str, Enum):
    RDP = 'rdp'
    VNC = 'vnc'
    TEAMVIEWER = 'teamviewer'
    VNC_TAILSCALE = 'vnc+tailscale'
    VNC_WIREGUARD = 'vnc+wireguard'
    RDP_WIREGUARD = 'rdp_wireguard'
    RDP_TAILSCALE = 'rdp+tailscale'
    RDP_OPENVPN = 'rdp+openvpn'


class Target(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    type: TargetType
    host: str
    username: Optional[str] = None
    password: str
    port: Optional[int] = None
    vpn_config: Optional[str] = None
    vpn_username: Optional[str] = None
    vpn_password: Optional[str] = None
    width: int = 1024
    height: int = 768
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_archived: bool = False
    # RDP customization
    rdp_params: Optional[str] = None
    queue_status: Optional[str] = (
        None  # Added field for queue status: "running" or "paused"
    )
    blocking_jobs: Optional[List[Dict[str, Any]]] = (
        None  # List of jobs blocking execution
    )
    has_blocking_jobs: Optional[bool] = (
        False  # Flag indicating if there are blocking jobs
    )
    blocking_jobs_count: Optional[int] = 0  # Count of blocking jobs
    has_active_session: Optional[bool] = False
    has_initializing_session: Optional[bool] = False


class TargetCreate(BaseModel):
    name: str
    type: TargetType
    host: str
    username: Optional[str] = None
    password: str
    port: Optional[int] = None
    vpn_config: Optional[str] = None
    vpn_username: Optional[str] = None
    vpn_password: Optional[str] = None
    width: int = 1024
    height: int = 768
    # RDP customization
    rdp_params: Optional[str] = None


class TargetUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[TargetType] = None
    host: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    vpn_config: Optional[str] = None
    vpn_username: Optional[str] = None
    vpn_password: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    # RDP customization
    rdp_params: Optional[str] = None


class Session(BaseModel):
    """Session model for API responses."""

    id: UUID
    name: str
    description: Optional[str] = None
    target_id: UUID
    status: str
    state: str = 'initializing'
    container_id: Optional[str] = None
    container_ip: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False
    archive_reason: Optional[str] = None
    last_job_time: Optional[datetime] = None


class SessionCreate(BaseModel):
    """Session creation model."""

    name: str
    description: Optional[str] = None
    target_id: UUID


class SessionUpdate(BaseModel):
    """Session update model."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    state: Optional[str] = None
    container_id: Optional[str] = None
    container_ip: Optional[str] = None


class JobStatus(str, Enum):
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    PAUSED = 'paused'
    SUCCESS = 'success'
    ERROR = 'error'
    CANCELED = 'canceled'


class APIResponse(BaseModel):
    """Model for API execution response."""

    status: JobStatus
    reason: Optional[str] = None
    extraction: Optional[Dict[str, Any]] = None
    exchanges: List[Dict[str, Any]] = []


# Recording Models
class RecordingRequest(BaseModel):
    """Request model for starting a recording"""

    framerate: Optional[int] = 30
    quality: Optional[str] = (
        'ultrafast'  # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    )
    format: Optional[str] = 'mp4'  # mp4, avi, mkv


class InputLogEntry(BaseModel):
    """Model for individual input log entries"""

    timestamp: str
    session_id: str
    source: str  # 'api' or 'vnc'
    action_type: str
    details: Dict[str, Any]


class RecordingStatus(StrEnum):
    STARTED = 'started'
    STOPPED = 'stopped'
    COMPLETED = 'completed'
    RECORDING = 'recording'


class RecordingResultResponse(BaseModel):
    status: RecordingStatus
    message: str
    recording_id: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    base64_video: str
    input_logs: Optional[List[InputLogEntry]] = None


class RecordingStatusResponse(BaseModel):
    status: RecordingStatus
    message: str
    recording_id: Optional[str] = None
    session_id: Optional[str] = None
    file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    start_time: Optional[str] = None


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target_id: UUID
    session_id: Optional[UUID] = (
        None  # Now optional, used when job is executed in a specific session
    )
    api_name: str
    parameters: Dict[str, Union[str, List[Any]]] = {}
    status: JobStatus = JobStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    api_exchanges: List[Dict[str, Any]] = []
    api_definition_version_id: Optional[UUID] = None
    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    duration_seconds: Optional[float] = None  # Duration in seconds


class JobCreate(BaseModel):
    api_name: str
    parameters: Dict[str, Union[str, List[Any]]] = {}
    status: JobStatus = JobStatus.PENDING


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SessionContainerLogs(BaseModel):
    session_id: str
    container_id: str
    logs: str
    lines_retrieved: int
    max_lines_requested: int
