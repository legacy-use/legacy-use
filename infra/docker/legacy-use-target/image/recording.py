from enum import StrEnum
import os
import asyncio
import base64
import json
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any, List

# Create router for recording endpoints
router = APIRouter(prefix='/recording', tags=['recording'])

# Recording state
recording_process = None
recording_file = None
vnc_monitor_process = None
current_recording_session_id = None
recording_start_time = None


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
    capture_vnc_input: Optional[bool] = True


class InputLogEntry(BaseModel):
    timestamp: str
    session_id: str
    source: Literal['api', 'vnc']  # Track whether input came from API or VNC user
    action_type: str
    details: Dict[str, Any]


class RecordingStatus(StrEnum):
    STARTED = 'started'
    STOPPED = 'stopped'
    COMPLETED = 'completed'
    RECORDING = 'recording'


class RecordingStatusResponse(BaseModel):
    status: RecordingStatus
    message: str
    recording_id: Optional[str] = None
    vnc_monitoring: Optional[bool] = None
    session_id: Optional[str] = None
    file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    start_time: Optional[str] = None


class RecordingResultResponse(BaseModel):
    status: RecordingStatus
    message: str
    recording_id: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    base64_video: Optional[str] = None
    input_logs: Optional[List[InputLogEntry]] = None


class InputLogSession(BaseModel):
    session_id: str
    file_size_bytes: int
    created_at: str
    modified_at: str
    action_count: int


class InputLogResponse(BaseModel):
    session_id: str
    total_actions: int
    logs: List[InputLogEntry]


class InputLogListResponse(BaseModel):
    sessions: list[InputLogSession]


async def start_vnc_input_monitoring(session_id: str) -> bool:
    """Start monitoring VNC input events using X11 event capture"""
    global vnc_monitor_process

    try:
        # Create input log directory
        log_dir = Path('/tmp/input_logs')
        log_dir.mkdir(exist_ok=True)

        # Create a script to monitor X11 events and convert them to our log format
        monitor_script = f"""#!/bin/bash
DISPLAY_NUM={os.getenv('DISPLAY_NUM', '1')}
SESSION_ID="{session_id}"
LOG_FILE="/tmp/input_logs/input_log_$SESSION_ID.jsonl"

# Function to log VNC input events
log_event() {{
    local event_type="$1"
    local details="$2"
    local timestamp=$(date -Iseconds)

    echo "{{\\"timestamp\\":\\"$timestamp\\",\\"session_id\\":\\"$SESSION_ID\\",\\"source\\":\\"vnc\\",\\"action_type\\":\\"$event_type\\",\\"details\\":$details}}" >> "$LOG_FILE"
}}

# Monitor mouse events using xinput
xinput list --id-only | while read device_id; do
    if xinput list-props "$device_id" 2>/dev/null | grep -q "Device Enabled"; then
        xinput test "$device_id" 2>/dev/null | while read line; do
            case "$line" in
                *"button press"*)
                    button=$(echo "$line" | grep -o 'button [0-9]*' | cut -d' ' -f2)
                    log_event "vnc_click" "{{\\"button\\":$button,\\"press\\":true}}"
                    ;;
                *"button release"*)
                    button=$(echo "$line" | grep -o 'button [0-9]*' | cut -d' ' -f2)
                    log_event "vnc_click" "{{\\"button\\":$button,\\"press\\":false}}"
                    ;;
                *"motion"*)
                    coords=$(echo "$line" | grep -o '[0-9]*\\.[0-9]*,[0-9]*\\.[0-9]*')
                    if [ ! -z "$coords" ]; then
                        x=$(echo "$coords" | cut -d',' -f1)
                        y=$(echo "$coords" | cut -d',' -f2)
                        log_event "vnc_mouse_move" "{{\\"x\\":$x,\\"y\\":$y}}"
                    fi
                    ;;
                *"key press"*)
                    key=$(echo "$line" | grep -o 'key [0-9]*' | cut -d' ' -f2)
                    log_event "vnc_key" "{{\\"key\\":$key,\\"press\\":true}}"
                    ;;
                *"key release"*)
                    key=$(echo "$line" | grep -o 'key [0-9]*' | cut -d' ' -f2)
                    log_event "vnc_key" "{{\\"key\\":$key,\\"press\\":false}}"
                    ;;
            esac
        done &
    fi
done

# Also monitor using xev for more detailed events
DISPLAY=:$DISPLAY_NUM xev -root -event mouse -event keyboard 2>/dev/null | while read line; do
    case "$line" in
        *"ButtonPress"*)
            if echo "$line" | grep -q "button"; then
                button=$(echo "$line" | grep -o 'button [0-9]*' | cut -d' ' -f2)
                x=$(echo "$line" | grep -o 'x [0-9]*' | cut -d' ' -f2)
                y=$(echo "$line" | grep -o 'y [0-9]*' | cut -d' ' -f2)
                log_event "vnc_button_press" "{{\\"button\\":$button,\\"x\\":$x,\\"y\\":$y}}"
            fi
            ;;
        *"ButtonRelease"*)
            if echo "$line" | grep -q "button"; then
                button=$(echo "$line" | grep -o 'button [0-9]*' | cut -d' ' -f2)
                log_event "vnc_button_release" "{{\\"button\\":$button}}"
            fi
            ;;
        *"KeyPress"*)
            if echo "$line" | grep -q "keycode"; then
                keycode=$(echo "$line" | grep -o 'keycode [0-9]*' | cut -d' ' -f2)
                log_event "vnc_key_press" "{{\\"keycode\\":$keycode}}"
            fi
            ;;
        *"KeyRelease"*)
            if echo "$line" | grep -q "keycode"; then
                keycode=$(echo "$line" | grep -o 'keycode [0-9]*' | cut -d' ' -f2)
                log_event "vnc_key_release" "{{\\"keycode\\":$keycode}}"
            fi
            ;;
        *"MotionNotify"*)
            if echo "$line" | grep -q "x [0-9]"; then
                x=$(echo "$line" | grep -o 'x [0-9]*' | cut -d' ' -f2)
                y=$(echo "$line" | grep -o 'y [0-9]*' | cut -d' ' -f2)
                log_event "vnc_motion" "{{\\"x\\":$x,\\"y\\":$y}}"
            fi
            ;;
    esac
done &

wait
"""

        # Write the monitoring script
        script_path = Path(f'/tmp/vnc_monitor_{session_id}.sh')
        with open(script_path, 'w') as f:
            f.write(monitor_script)
        script_path.chmod(0o755)

        # Start the monitoring process
        vnc_monitor_process = await asyncio.create_subprocess_exec(
            'bash',
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Give it a moment to start
        await asyncio.sleep(0.5)

        # Check if process is still running
        if vnc_monitor_process.returncode is not None:
            return False

        return True

    except Exception as e:
        print(f'Failed to start VNC input monitoring: {e}')
        return False


async def stop_vnc_input_monitoring():
    """Stop VNC input monitoring"""
    global vnc_monitor_process, current_recording_session_id

    if vnc_monitor_process is not None:
        try:
            # Send SIGTERM for graceful shutdown
            vnc_monitor_process.terminate()

            # Wait for process to finish with timeout
            try:
                await asyncio.wait_for(vnc_monitor_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                vnc_monitor_process.kill()
                await vnc_monitor_process.wait()

        except Exception as e:
            print(f'Error stopping VNC monitor: {e}')
        finally:
            vnc_monitor_process = None

            # Clean up monitor script
            if current_recording_session_id:
                script_path = Path(
                    f'/tmp/vnc_monitor_{current_recording_session_id}.sh'
                )
                if script_path.exists():
                    script_path.unlink()


async def get_session_input_logs(session_id: str) -> List[InputLogEntry]:
    """Get input logs for a specific session"""
    log_file = Path(f'/tmp/input_logs/input_log_{session_id}.jsonl')

    if not log_file.exists():
        return []

    try:
        logs = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    log_data = json.loads(line.strip())
                    logs.append(InputLogEntry(**log_data))
        return logs
    except Exception as e:
        print(f'Error reading input logs: {e}')
        return []


@router.post('/start', response_model=RecordingStatusResponse)
async def start_recording(
    request: RecordingRequest | None = None,
) -> RecordingStatusResponse:
    """Start screen recording using FFmpeg"""
    global \
        recording_process, \
        recording_file, \
        current_recording_session_id, \
        recording_start_time

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
        '-pix_fmt',
        'yuv420p',
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

        # Record start time
        recording_start_time = datetime.now()

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

        # Start VNC input monitoring if requested
        if request.capture_vnc_input:
            current_recording_session_id = recording_id
            await start_vnc_input_monitoring(recording_id)

        return RecordingStatusResponse(
            status=RecordingStatus.STARTED,
            message='Screen recording started successfully',
            recording_id=recording_id,
            file_path=str(recording_file),
            vnc_monitoring=request.capture_vnc_input,
        )

    except Exception as e:
        recording_process = None
        recording_file = None
        raise HTTPException(
            status_code=500, detail=f'Failed to start recording: {str(e)}'
        )


@router.post('/stop', response_model=RecordingResultResponse)
async def stop_recording() -> RecordingResultResponse:
    """Stop screen recording and return the video file"""
    global \
        recording_process, \
        recording_file, \
        current_recording_session_id, \
        recording_start_time

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

        # Stop VNC input monitoring
        await stop_vnc_input_monitoring()

        # Check if recording file exists and get info
        if recording_file and recording_file.exists():
            file_size = recording_file.stat().st_size

            # Read file and encode to base64
            with open(recording_file, 'rb') as f:
                video_data = f.read()
            base64_video = base64.b64encode(video_data).decode('utf-8')

            # Extract recording ID from filename
            recording_id = recording_file.stem.replace('recording_', '')

            # Get input logs
            input_logs = await get_session_input_logs(recording_id)

            response = RecordingResultResponse(
                status=RecordingStatus.COMPLETED,
                message='Recording stopped successfully',
                recording_id=recording_id,
                file_size_bytes=file_size,
                base64_video=base64_video,
                input_logs=input_logs,
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
        recording_start_time = None

        # Also stop VNC monitoring on error
        await stop_vnc_input_monitoring()
        current_recording_session_id = None

        raise HTTPException(
            status_code=500, detail=f'Failed to stop recording: {str(e)}'
        )
    finally:
        # Clean up global state
        recording_process = None
        temp_file = recording_file
        recording_file = None
        recording_start_time = None
        current_recording_session_id = None

        # Remove the file after encoding to base64
        if temp_file and temp_file.exists():
            temp_file.unlink()


@router.get('/status', response_model=RecordingStatusResponse)
async def get_recording_status() -> RecordingStatusResponse:
    """Get current recording status"""
    global \
        recording_process, \
        recording_file, \
        vnc_monitor_process, \
        current_recording_session_id, \
        recording_start_time

    if recording_process is None:
        return RecordingStatusResponse(
            status=RecordingStatus.STOPPED,
            message='Recording stopped',
            vnc_monitoring=False,
        )

    # Check if process is still running
    if recording_process.returncode is not None:
        # Process has terminated
        recording_process = None
        recording_file = None
        recording_start_time = None
        await stop_vnc_input_monitoring()
        current_recording_session_id = None
        return RecordingStatusResponse(
            status=RecordingStatus.STOPPED,
            message='Recording stopped',
            vnc_monitoring=False,
        )

    # Calculate duration if recording is active
    duration_seconds = None
    if recording_start_time:
        duration_seconds = (datetime.now() - recording_start_time).total_seconds()

    return RecordingStatusResponse(
        status=RecordingStatus.RECORDING,
        message='Recording in progress',
        vnc_monitoring=vnc_monitor_process is not None
        and vnc_monitor_process.returncode is None,
        session_id=current_recording_session_id,
        file_path=str(recording_file) if recording_file else None,
        duration_seconds=duration_seconds,
        start_time=recording_start_time.isoformat() if recording_start_time else None,
    )
