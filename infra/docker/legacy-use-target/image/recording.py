import os
import asyncio
import base64
import json
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional

# Create router for recording endpoints
router = APIRouter(prefix='/recording', tags=['recording'])

# Recording state
recording_process = None
recording_file = None


class RecordingRequest(BaseModel):
    framerate: Optional[int] = 30
    quality: Optional[
        Literal[
            'ultrafast',
            'superfast',
            'veryfast',
            'faster',
            'fast',
            'medium',
            'slow',
            'slower',
            'veryslow',
        ]
    ] = 'ultrafast'
    format: Optional[Literal['mp4', 'avi', 'mkv']] = 'mp4'


class RecordingResponse(BaseModel):
    status: str
    message: str
    recording_id: Optional[str] = None
    file_path: Optional[str] = None


class RecordingStopResponse(BaseModel):
    status: str
    message: str
    recording_id: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    base64_video: Optional[str] = None


class InputLogSession(BaseModel):
    session_id: str
    file_size_bytes: int
    created_at: str
    modified_at: str
    action_count: int


class InputLogResponse(BaseModel):
    session_id: str
    total_actions: int
    logs: list[dict]


class InputLogListResponse(BaseModel):
    sessions: list[InputLogSession]


@router.post('/start', response_model=RecordingResponse)
async def start_recording(request: RecordingRequest | None = None) -> RecordingResponse:
    """Start screen recording using FFmpeg"""
    global recording_process, recording_file

    if request is None:
        request = RecordingRequest()

    if recording_process is not None:
        raise HTTPException(status_code=400, detail='Recording is already in progress')

    # Get display settings
    display_num = os.getenv('DISPLAY_NUM', '1')
    width = os.getenv('WIDTH', '1024')
    height = os.getenv('HEIGHT', '768')

    # Generate unique recording ID and file path
    recording_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path('/tmp/recordings')
    output_dir.mkdir(exist_ok=True)
    recording_file = output_dir / f'recording_{recording_id}.{request.format}'

    # Build FFmpeg command
    ffmpeg_cmd = [
        'ffmpeg',
        '-f',
        'x11grab',
        '-r',
        str(request.framerate),
        '-s',
        f'{width}x{height}',
        '-i',
        f':{display_num}',
        '-c:v',
        'libx264',
        '-preset',
        request.quality,
        '-crf',
        '23',
        '-y',  # Overwrite output file
        str(recording_file),
    ]

    try:
        # Start FFmpeg process
        recording_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # Give it a moment to start
        await asyncio.sleep(1)

        # Check if process is still running
        if recording_process.returncode is not None:
            stdout, stderr = await recording_process.communicate()
            recording_process = None
            recording_file = None
            raise HTTPException(
                status_code=500, detail=f'Failed to start recording: {stderr.decode()}'
            )

        return RecordingResponse(
            status='started',
            message='Screen recording started successfully',
            recording_id=recording_id,
            file_path=str(recording_file),
        )

    except Exception as e:
        recording_process = None
        recording_file = None
        raise HTTPException(
            status_code=500, detail=f'Failed to start recording: {str(e)}'
        )


@router.post('/stop', response_model=RecordingStopResponse)
async def stop_recording() -> RecordingStopResponse:
    """Stop screen recording and return the video file"""
    global recording_process, recording_file

    if recording_process is None:
        raise HTTPException(
            status_code=400, detail='No recording is currently in progress'
        )

    try:
        # Send SIGTERM to FFmpeg for graceful shutdown
        recording_process.terminate()

        # Wait for process to finish with timeout
        try:
            await asyncio.wait_for(recording_process.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            # Force kill if it doesn't terminate gracefully
            recording_process.kill()
            await recording_process.wait()

        # Check if recording file exists and get info
        if recording_file and recording_file.exists():
            file_size = recording_file.stat().st_size

            # Read file and encode to base64
            with open(recording_file, 'rb') as f:
                video_data = f.read()
            base64_video = base64.b64encode(video_data).decode('utf-8')

            # Extract recording ID from filename
            recording_id = recording_file.stem.replace('recording_', '')

            response = RecordingStopResponse(
                status='completed',
                message='Recording stopped successfully',
                recording_id=recording_id,
                file_size_bytes=file_size,
                base64_video=base64_video,
            )

            # Clean up
            recording_process = None
            temp_file = recording_file
            recording_file = None

            # Remove the file after encoding to base64
            temp_file.unlink()

            return response
        else:
            raise HTTPException(
                status_code=500, detail='Recording file not found or empty'
            )

    except Exception as e:
        # Clean up on error
        recording_process = None
        if recording_file and recording_file.exists():
            recording_file.unlink()
        recording_file = None

        raise HTTPException(
            status_code=500, detail=f'Failed to stop recording: {str(e)}'
        )


@router.get('/status')
async def get_recording_status():
    """Get current recording status"""
    global recording_process, recording_file

    if recording_process is None:
        return {'status': 'stopped', 'recording': False}

    # Check if process is still running
    if recording_process.returncode is not None:
        # Process has terminated
        recording_process = None
        recording_file = None
        return {'status': 'stopped', 'recording': False}

    return {
        'status': 'recording',
        'recording': True,
        'file_path': str(recording_file) if recording_file else None,
    }


@router.get('/input_logs/{session_id}', response_model=InputLogResponse)
async def get_input_logs(session_id: str) -> InputLogResponse:
    """Get input logs for a specific session"""
    log_file = Path(f'/tmp/input_logs/input_log_{session_id}.jsonl')

    if not log_file.exists():
        raise HTTPException(
            status_code=404, detail=f'Input log for session {session_id} not found'
        )

    try:
        logs = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line.strip()))

        return InputLogResponse(
            session_id=session_id, total_actions=len(logs), logs=logs
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f'Failed to read input logs: {str(e)}'
        )


@router.get('/input_logs', response_model=InputLogListResponse)
async def list_input_log_sessions() -> InputLogListResponse:
    """List all available input log sessions"""
    log_dir = Path('/tmp/input_logs')

    if not log_dir.exists():
        return InputLogListResponse(sessions=[])

    sessions = []
    for log_file in log_dir.glob('input_log_*.jsonl'):
        session_id = log_file.stem.replace('input_log_', '')
        file_stats = log_file.stat()

        # Count lines to get action count
        action_count = 0
        try:
            with open(log_file, 'r') as f:
                action_count = sum(1 for line in f if line.strip())
        except:
            action_count = 0

        sessions.append(
            InputLogSession(
                session_id=session_id,
                file_size_bytes=file_stats.st_size,
                created_at=datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                modified_at=datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                action_count=action_count,
            )
        )

    # Sort by creation time, newest first
    sessions.sort(key=lambda x: x.created_at, reverse=True)

    return InputLogListResponse(sessions=sessions)
